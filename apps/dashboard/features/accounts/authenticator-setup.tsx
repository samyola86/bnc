"use client";

import { QRCodeSVG } from "qrcode.react";

export function AuthenticatorSetup({ uri }: { uri: string }) {
  const secret = new URL(uri).searchParams.get("secret");
  return <div className="space-y-4 rounded border bg-muted p-4 text-sm">
    <p>Open your authenticator app, choose Add account, then scan this QR code.</p>
    <div className="mx-auto w-fit max-w-full rounded bg-white p-2">
      <QRCodeSVG value={uri} size={240} marginSize={4} level="M" title="Scan to add your BNC authenticator" role="img" className="h-auto max-w-full" />
    </div>
    <p>After scanning, enter the six-digit code below to finish setup.</p>
    <details><summary className="cursor-pointer">Can’t scan? Set up manually</summary>
      <div className="mt-3 space-y-3">
        <p>Choose a time-based account in your authenticator. Use this setup key:</p>
        <code className="block break-all select-all rounded bg-background p-2">{secret}</code>
        <p>Use 6 digits and a 30-second interval.</p>
        <a className="block text-primary underline" href={uri}>Open in an authenticator on this device</a>
      </div>
    </details>
  </div>;
}
