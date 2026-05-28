import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'stockfolio',
  description: '주식 투자 포트폴리오 관리',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  )
}
