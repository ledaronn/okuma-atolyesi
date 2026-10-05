# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Report it privately from the
[Security tab](https://github.com/ledaronn/okuma-atolyesi/security) → **Report a vulnerability**.

Include the Okuma Atölyesi version, your Windows version, the steps to reproduce and, if possible,
a sample file. You will get an answer within 14 days.

## Supported versions

Only the latest release receives security fixes.

## What is in scope

- A crafted PDF or `.docx` that crashes the app in a way an attacker can control, runs code, or
  reads/writes files outside the library folder.
- The MCP server (`server.py` / `--mcp`) returning data outside the library or the allowed import
  folders, or accepting commands it should not.
- Text inside documents being treated as instructions by the AI connection instead of as data.
- The editor overwriting an original Word file with content loss despite the protection described
  in the README.

---

**Türkçe:** Güvenlik açıklarını herkese açık bir "issue" olarak değil, deponun **Security** sekmesindeki
**Report a vulnerability** ile gizli olarak bildir. 14 gün içinde yanıt verilir.
