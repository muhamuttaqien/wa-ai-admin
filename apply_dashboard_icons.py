from pathlib import Path

base = Path("dashboard/templates/base.html")
lead = Path("dashboard/templates/lead.html")
css = Path("dashboard/static/dashboard.css")

for p in (base, lead, css):
    if not p.exists():
        raise SystemExit(f"File tidak ditemukan: {p}")

s = base.read_text()
fa = '  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">\n'
if "cdnjs.cloudflare.com/ajax/libs/font-awesome/" not in s:
    s = s.replace("</head>", fa + "</head>", 1)

s = s.replace("↻ Refresh", '<i class="fa-solid fa-rotate-right" aria-hidden="true"></i><span>Refresh</span>')
s = s.replace("👤 Admin B2C", '<i class="fa-solid fa-user" aria-hidden="true"></i><span>Admin B2C</span>')
s = s.replace("🏢 Admin B2B", '<i class="fa-solid fa-building" aria-hidden="true"></i><span>Admin B2B</span>')

if "fa-rotate-right" not in s:
    needle = '<a class="{{ \'active\' if channel==\'B2C\' else \'\' }}" href="{{ url_for(\'b2c\') }}">'
    refresh = '<a class="nav-refresh" href="javascript:window.location.reload()" title="Refresh halaman"><i class="fa-solid fa-rotate-right" aria-hidden="true"></i><span>Refresh</span></a>\n    '
    if needle not in s:
        raise SystemExit("Link Admin B2C tidak ditemukan di base.html")
    s = s.replace(needle, refresh + needle, 1)
base.write_text(s)

s = lead.read_text()
s = s.replace("← Kembali", '<i class="fa-solid fa-arrow-left" aria-hidden="true"></i><span>Kembali</span>')
s = s.replace("👤 Human Handling", '<i class="fa-solid fa-user-shield" aria-hidden="true"></i><span>Human Handling</span>')
s = s.replace("Kirim ke WhatsApp ➤", '<i class="fa-brands fa-whatsapp" aria-hidden="true"></i><span>Kirim ke WhatsApp</span>')
s = s.replace(
    "🔒 Human reply hanya tersedia ketika ada notifikasi aktif untuk lead ini.",
    '<i class="fa-solid fa-lock" aria-hidden="true"></i><span>Human reply hanya tersedia ketika ada notifikasi aktif untuk lead ini.</span>'
)
lead.write_text(s)

s = css.read_text()
block = '''
/* Consistent Font Awesome icon treatment */
nav a,
.back,
.human-send,
.human-reply-locked {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

nav a i,
.back i,
.human-send i,
.human-reply-locked i,
.human-reply-head strong i {
  width: 1em;
  text-align: center;
  flex: 0 0 auto;
}

.human-reply-head strong {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.nav-refresh i {
  transition: transform .2s ease;
}

.nav-refresh:hover i {
  transform: rotate(35deg);
}
'''
if "/* Consistent Font Awesome icon treatment */" not in s:
    s = s.rstrip() + "\n\n" + block.strip() + "\n"
css.write_text(s)

print("✓ Font Awesome diterapkan secara konsisten.")
print("✓ Refresh berada di kiri Admin B2C.")
print("✓ Ikon diperbarui: Refresh, Admin B2C, Admin B2B, Kembali, Human Handling, Kirim WhatsApp, Lock.")
