"""Authenticate first, then parse one size-bounded multipart file incrementally."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.core.config import Settings
from app.services.domain_common import DomainError
from app.services.upload_service import validate_upload_name


class VideoMultipartParser(MultiPartParser):
    def __init__(self, *args, size_limit: int, **kwargs):
        super().__init__(*args, max_files=1, max_fields=0, **kwargs)
        self.size_limit = size_limit
        self.file_bytes = 0
        self.header_bytes = 0
        self.finished = False

    def _count_header(self, size: int) -> None:
        self.header_bytes += size
        if self.header_bytes > 16 * 1024:
            raise DomainError(422, "Multipart headers are too large.")

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._count_header(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._count_header(end - start)
        super().on_header_value(data, start, end)

    def on_headers_finished(self) -> None:
        super().on_headers_finished()
        part = self._current_part
        if part.field_name != "file" or part.file is None:
            raise DomainError(422, "Send one video in the multipart field named file.")
        validate_upload_name(part.file.filename, part.file.content_type)

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        self.file_bytes += end - start
        if self.file_bytes > self.size_limit:
            raise DomainError(
                413, "The video exceeds the configured upload size limit."
            )
        super().on_part_data(data, start, end)

    def on_end(self) -> None:
        self.finished = True


@asynccontextmanager
async def parse_video_upload(
    request: Request, settings: Settings
) -> AsyncIterator[UploadFile]:
    content_type = request.headers.get("content-type", "")
    if (
        not content_type.lower().startswith("multipart/form-data;")
        or len(content_type) > 1024
    ):
        raise DomainError(415, "Send the video as multipart/form-data.")
    # Multipart overhead is bounded separately; the file limit is exact above.
    total_limit = settings.max_upload_size + 64 * 1024
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
            if length < 0:
                raise ValueError
        except ValueError:
            raise DomainError(400, "Invalid upload content length.") from None
        if length > total_limit:
            raise DomainError(
                413, "The video exceeds the configured upload size limit."
            )

    async def limited_stream() -> AsyncIterator[bytes]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > total_limit:
                raise DomainError(
                    413, "The video exceeds the configured upload size limit."
                )
            yield chunk

    parser = VideoMultipartParser(
        request.headers, limited_stream(), size_limit=settings.max_upload_size
    )
    form: FormData | None = None
    try:
        # Starlette spools large parts to disk, closing them on parse/stream errors.
        form = await parser.parse()
        if not parser.finished:
            raise DomainError(422, "The upload was incomplete. Try again.")
        file = form.get("file")
        if len(form.multi_items()) != 1 or not isinstance(file, UploadFile):
            raise DomainError(422, "Select exactly one video file.")
        yield file
    except MultiPartException:
        raise DomainError(422, "Send exactly one valid multipart video file.") from None
    finally:
        if form is not None:
            await form.close()
