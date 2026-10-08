import { House, MapPinOff } from 'lucide-react'
import { Link } from 'react-router'
import { MessagePanel } from '../components/MessagePanel'

export function NotFoundPage() {
  return <MessagePanel icon={MapPinOff} title="Page not found"
    actions={<Link to="/" className="button-primary"><House aria-hidden="true" className="size-4" />Return home</Link>}>
    <p>This page is unavailable. Check the address or use the navigation.</p>
  </MessagePanel>
}
