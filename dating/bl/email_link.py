"""Business logic for passwordless email sign-in.

Mints a Firebase magic link, wraps it in a branded HTML email, and sends it via
the Brevo email service — so the user gets a hintder-styled message from our own
domain instead of Firebase's plain default.
"""

from dating.services.email import EmailService
from dating.services.firebase import generate_email_sign_in_link

_SUBJECT = "Your hintder sign-in link"


def _render_email(link: str) -> str:
    """Return the branded HTML for the sign-in email (email-client-safe markup)."""
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#08070A;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#08070A;padding:40px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:460px;background:#100D16;border:1px solid rgba(255,255,255,0.06);
                      border-radius:20px;overflow:hidden;">
          <tr><td style="padding:36px 36px 8px 36px;">
            <div style="font-family:Georgia,'Times New Roman',serif;font-size:18px;
                        font-weight:bold;color:#ffffff;letter-spacing:-0.3px;">
              <span style="color:#FF4D6D;">&#9670;</span>&nbsp;hintder
            </div>
          </td></tr>
          <tr><td style="padding:20px 36px 0 36px;">
            <h1 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:30px;
                       line-height:1.2;font-weight:normal;color:#ffffff;">
              Sign in, <span style="font-style:italic;color:#FF7A59;">instantly.</span>
            </h1>
            <p style="margin:16px 0 0 0;font-family:Georgia,'Times New Roman',serif;
                      font-size:15px;line-height:1.55;color:#A7A1B0;">
              Tap below to sign in to hintder. The link works once and expires
              shortly &mdash; no password needed.
            </p>
          </td></tr>
          <tr><td style="padding:28px 36px 8px 36px;">
            <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
              <tr><td align="center" bgcolor="#FE3C72"
                      style="border-radius:999px;
                             background:linear-gradient(95deg,#FE3C72,#FF6B6B 50%,#FF8552);">
                <a href="{link}" target="_blank"
                   style="display:block;padding:16px 24px;font-family:Georgia,serif;
                          font-size:16px;font-style:italic;color:#ffffff;
                          text-decoration:none;font-weight:bold;">
                  Sign in to hintder &nbsp;&rarr;
                </a>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:18px 36px 0 36px;">
            <p style="margin:0;font-family:Georgia,serif;font-size:12px;line-height:1.5;
                      color:#6E6878;">
              Or paste this link into your browser:
            </p>
            <p style="margin:6px 0 0 0;font-family:Georgia,serif;font-size:12px;
                      line-height:1.5;word-break:break-all;">
              <a href="{link}" style="color:#FF7A59;text-decoration:none;">{link}</a>
            </p>
          </td></tr>
          <tr><td style="padding:28px 36px 36px 36px;">
            <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:0 0 16px 0;"/>
            <p style="margin:0;font-family:Georgia,serif;font-size:12px;line-height:1.5;
                      color:#6E6878;">
              Didn't request this? You can safely ignore this email &mdash; no one
              can sign in without the link above.
            </p>
            <p style="margin:12px 0 0 0;font-family:Georgia,serif;font-size:12px;
                      font-style:italic;color:#4F4A58;">
              hintder &middot; built for the moment before she replies.
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


async def send_sign_in_email(email_svc: EmailService, email: str, continue_url: str) -> bool:
    """Mint a magic link for ``email`` and send the branded sign-in email."""
    link = generate_email_sign_in_link(email, continue_url)
    return await email_svc.send_html(to=email, subject=_SUBJECT, html=_render_email(link))
