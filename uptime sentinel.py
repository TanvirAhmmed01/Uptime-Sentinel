"""
1st step
"""

import html
import smtplib
import socket
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 5000            
TIMEOUT = 10           
SSL_WARN_DAYS = 14     
REFRESH = 15           
DB_FILE = "sentinel.db"


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = ""         
SMTP_PASSWORD = ""    


FIRST_RUN_SITES = [("Google", "https://www.google.com", 60),
                   ("GitHub", "https://github.com", 60)]

monitoring = True      
log_lines = []         


def log(message):
    """ """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.insert(0, f"[{now}] {message}")
    del log_lines[50:]                       
    print(message)




def db(sql, values=(), fetch=None):
    """
   
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row               
    result = conn.execute(sql, values)
    data = result.fetchone() if fetch == "one" else result.fetchall() if fetch == "all" else None
    conn.commit()
    conn.close()
    return data


def setup_database():
    """ """
    db("""CREATE TABLE IF NOT EXISTS sites (
              id INTEGER PRIMARY KEY, name TEXT, url TEXT, interval INTEGER)""")
    db("""CREATE TABLE IF NOT EXISTS checks (
              site_id INTEGER, time TEXT, status TEXT,
              code INTEGER, seconds REAL, error TEXT)""")
    db("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")

    if db("SELECT COUNT(*) AS n FROM sites", fetch="one")["n"] == 0:
        for name, url, interval in FIRST_RUN_SITES:
            db("INSERT INTO sites (name, url, interval) VALUES (?, ?, ?)",
               (name, url, interval))


def get_sites():
    return db("SELECT * FROM sites ORDER BY id", fetch="all")


def get_email():
    """ """
    row = db("SELECT value FROM settings WHERE key = 'email'", fetch="one")
    return row["value"] if row else ""


def get_stats(site_id):
    """ """
    row = db("""SELECT COUNT(*) AS total,
                       SUM(status = 'UP') AS up,
                       AVG(CASE WHEN status = 'UP' THEN seconds END) AS average
                FROM checks
                WHERE site_id = ? AND time >= datetime('now', 'localtime', '-7 days')""",
             (site_id,), fetch="one")

    total, up = row["total"], row["up"] or 0
    return {"total": total, "up": up, "down": total - up,
            "uptime": round(up / total * 100, 1) if total else None,
            "average": round(row["average"], 2) if row["average"] else None}


def check_site(url):
    """Visit one website and report whether it is UP or DOWN."""
    start = time.time()
    try:
        answer = urllib.request.urlopen(url, timeout=TIMEOUT)
        code, error = answer.status, None
    except urllib.error.HTTPError as e:
        code, error = e.code, None           
    except Exception as e:                   
        code, error = None, type(e).__name__

    return {"status": "DOWN" if error else "UP",
            "code": code,
            "seconds": round(time.time() - start, 2) if not error else None,
            "error": "No response" if error else None,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def ssl_days_left(url):
    """."""
    address = urllib.parse.urlparse(url)
    if address.scheme != "https":
        return None
    try:
        with socket.create_connection((address.hostname, 443), TIMEOUT) as sock:
            with ssl.create_default_context().wrap_socket(
                    sock, server_hostname=address.hostname) as secure:
                expiry_text = secure.getpeercert()["notAfter"]
        expiry = datetime.strptime(expiry_text, "%b %d %H:%M:%S %Y %Z")
        return (expiry.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    except Exception:
        return None                          


def send_email(subject, message):
    """."""
    to_address = get_email()
    if not to_address:
        log("No alert email saved")
        return False
    if not SMTP_USER or not SMTP_PASSWORD:
        log("Email not sent: fill in SMTP_USER and SMTP_PASSWORD at the top of the file")
        return False
    try:
        mail = EmailMessage()
        mail["From"] = SMTP_USER
        mail["To"] = to_address
        mail["Subject"] = subject
        mail.set_content(message + "\n\n-- Uptime Sentinel")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT) as server:
            server.starttls()                 
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(mail)
        log(f"Email alert sent to {to_address}")
        return True
    except Exception as e:
        log(f"Email alert failed ({type(e).__name__})")
        return False




latest = {}        
due_at = {}        


def run_check(site):
    """ """
    result = check_site(site["url"])
    result["ssl_days"] = ssl_days_left(site["url"]) if result["status"] == "UP" else None

    db("INSERT INTO checks (site_id, time, status, code, seconds, error) "
       "VALUES (?, ?, ?, ?, ?, ?)",
       (site["id"], result["time"], result["status"],
        result["code"], result["seconds"], result["error"]))

    before = latest.get(site["id"])
    latest[site["id"]] = result

    if result["status"] == "UP":
        log(f"{site['name']} is UP ({result['seconds']}s)")
    else:
        log(f"{site['name']} is DOWN")

    
    if before and before["status"] != result["status"]:
        if result["status"] == "DOWN":
            send_email(f"🚨 {site['name']} is DOWN",
                       f"{site['name']} is not responding.\nURL: {site['url']}\nTime: {result['time']}")
        else:
            send_email(f"🟢 {site['name']} is back UP",
                       f"{site['name']} is responding again ({result['seconds']}s).\nURL: {site['url']}\nTime: {result['time']}")

    if result["ssl_days"] is not None and result["ssl_days"] <= SSL_WARN_DAYS:
        log(f"SSL warning: {site['name']} certificate expires in {result['ssl_days']} days")


def monitor_loop():
    """ ."""
    while True:
        if monitoring:
            for site in get_sites():
                if time.time() >= due_at.get(site["id"], 0):
                    due_at[site["id"]] = time.time() + site["interval"]
                    run_check(site)
        time.sleep(1)




CSS = """
body { background:#0d1117; color:#e6edf3; font-family:"Segoe UI",Arial,sans-serif;
       margin:0; }
header { background:#010409; border-bottom:1px solid #21262d; padding:22px 32px; }
header h1 { margin:0; font-size:24px; }
header p { color:#8b949e; font-size:14px; margin:4px 0 0; }
main { max-width:1150px; margin:0 auto; padding:26px 32px; }
.box { background:#161b22; border:1px solid #21262d; border-radius:10px;
       padding:16px 18px; margin-bottom:18px; }
.box h3 { margin:0 0 10px; font-size:15px; }
form { display:inline; }
.row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
input { background:#0d1117; border:1px solid #30363d; border-radius:6px;
        color:#e6edf3; padding:8px 10px; font-size:14px; }
.wide { flex:1; min-width:220px; }
button { background:#21262d; border:1px solid #30363d; border-radius:6px;
         color:#e6edf3; padding:8px 14px; font-size:14px; cursor:pointer; }
button:hover { background:#30363d; }
.green { background:#238636; border-color:#2ea043; }
.red { background:#8b2b2b; border-color:#f85149; }
.controls { display:flex; gap:10px; align-items:center; margin-bottom:20px;
            flex-wrap:wrap; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
         gap:18px; }
.card { background:#161b22; border:1px solid #21262d; border-left:4px solid #30363d;
        border-radius:10px; padding:18px; position:relative; }
.card.up { border-left-color:#2ea043; }
.card.down { border-left-color:#f85149; }
.card h2 { margin:0; font-size:17px; display:inline; }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%;
       margin-right:8px; }
.up .dot { background:#2ea043; } .down .dot { background:#f85149; }
.url { color:#8b949e; font-size:12px; margin:8px 0 12px; word-break:break-all; }
.line { font-size:14px; margin:0 0 5px; }
.name { color:#8b949e; display:inline-block; width:150px; }
.value { font-weight:bold; }
.ok { color:#2ea043; } .bad { color:#f85149; } .warn { color:#d29922; }
.small { color:#6e7681; font-size:12px; margin-top:10px; }
.x { position:absolute; top:10px; right:10px; }
.x button { background:none; border:none; color:#6e7681; font-size:15px; }
.x button:hover { color:#f85149; }
.log { background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:12px;
       font-family:Consolas,monospace; font-size:12px; line-height:1.7;
       max-height:200px; overflow-y:auto; color:#8b949e; }
footer { border-top:1px solid #21262d; color:#6e7681; font-size:12px;
         text-align:center; padding:16px; }
"""


def safe(text):
    """Escape text so it cannot break the page."""
    return html.escape(str(text))


def build_card(site):
    """"""
    result = latest.get(site["id"])
    stats = get_stats(site["id"])
    lines = []

    if result is None:
        colour = "down"
        lines.append('<p class="line"><span class="name">Status</span>'
                     '<span class="value warn">Not checked yet</span></p>')
    elif result["status"] == "UP":
        colour = "up"
        lines.append('<p class="line"><span class="name">Status</span>'
                     '<span class="value ok">UP</span></p>')
        lines.append(f'<p class="line"><span class="name">HTTP Code</span>'
                     f'<span class="value">{result["code"]}</span></p>')
        lines.append(f'<p class="line"><span class="name">Response Time</span>'
                     f'<span class="value">{result["seconds"]}s</span></p>')
    else:
        colour = "down"
        lines.append('<p class="line"><span class="name">Status</span>'
                     '<span class="value bad">DOWN</span></p>')
        lines.append(f'<p class="line"><span class="name">Error</span>'
                     f'<span class="value">{safe(result["error"])}</span></p>')

    if result and result["ssl_days"] is not None:
        warn = " warn" if result["ssl_days"] <= SSL_WARN_DAYS else ""
        lines.append(f'<p class="line"><span class="name">SSL expires in</span>'
                     f'<span class="value{warn}">{result["ssl_days"]} days</span></p>')

    if stats["total"]:
        lines.append(f'<p class="line"><span class="name">Checks (7 days)</span>'
                     f'<span class="value">{stats["total"]} '
                     f'({stats["up"]} up / {stats["down"]} down)</span></p>')
        lines.append(f'<p class="line"><span class="name">Uptime</span>'
                     f'<span class="value">{stats["uptime"]}%</span></p>')
        if stats["average"]:
            lines.append(f'<p class="line"><span class="name">Avg response</span>'
                         f'<span class="value">{stats["average"]}s</span></p>')

    when = f'Last checked: {result["time"]}' if result else f'Interval: {site["interval"]}s'

    return f"""
    <div class="card {colour}">
      <form class="x" method="post" action="/delete">
        <input type="hidden" name="id" value="{site['id']}">
        <button title="Remove">&#10005;</button>
      </form>
      <span class="dot"></span><h2>{safe(site['name'])}</h2>
      <p class="url">{safe(site['url'])}</p>
      {"".join(lines)}
      <p class="small">{when}</p>
    </div>"""


def build_page():
    """"""
    cards = "".join(build_card(site) for site in get_sites())
    logs = "<br>".join(safe(line) for line in log_lines) or "Ready."
    button = "Stop monitoring" if monitoring else "Start monitoring"
    state = "running" if monitoring else "stopped"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="{REFRESH}">
  <title>Uptime Sentinel</title>
  <style>{CSS}</style>
</head>
<body>
<header>
  <h1>Uptime Sentinel</h1>
</header>

<main>
  <div class="box">
    <h3>Add a website</h3>
    <form method="post" action="/add" class="row">
      <input name="name" placeholder="Name (e.g. GitHub)" required>
      <input name="url" class="wide" placeholder="https://example.com" required>
      <input name="interval" type="number" value="60" min="5" style="width:90px">
      <button class="green">Add website</button>
    </form>
  </div>

  <div class="box">
    <h3>Email alerts (optional &mdash; emailed when a website goes DOWN or comes back UP)</h3>
    <form method="post" action="/email" class="row">
      <input name="email" type="email" class="wide" value="{safe(get_email())}"
             placeholder="your@email.com (leave empty to disable)">
      <button name="action" value="save">Save</button>
      <button name="action" value="test">Send test alert</button>
    </form>
  </div>

  <div class="controls">
    <form method="post" action="/check"><button class="green">Check all now</button></form>
    <form method="post" action="/toggle"><button>{button}</button></form>
    <form method="post" action="/clear"><button class="red">Clear history</button></form>
    <span style="color:#8b949e;font-size:14px">Monitoring: <b class="ok">{state}</b></span>
  </div>

  <div class="cards">{cards}</div>

  <div class="box" style="margin-top:22px">
    <h3>Activity log</h3>
    <div class="log">{logs}</div>
  </div>
</main>

<footer>Uptime Sentinel &mdash; by Md Tanvir Ahmmed</footer>
</body>
</html>"""



class Server(BaseHTTPRequestHandler):

    def do_GET(self):
        """"""
        page = build_page().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        """"""
        global monitoring
        size = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(size).decode())
        value = lambda key: form.get(key, [""])[0].strip()

        if self.path == "/add":
            url = value("url")
            if not url.startswith("http"):
                url = "https://" + url
            db("INSERT INTO sites (name, url, interval) VALUES (?, ?, ?)",
               (value("name"), url, int(value("interval") or 60)))
            log(f"Added {value('name')}")

        elif self.path == "/delete":
            site_id = int(value("id"))
            db("DELETE FROM sites WHERE id = ?", (site_id,))
            db("DELETE FROM checks WHERE site_id = ?", (site_id,))
            latest.pop(site_id, None)
            log("Website removed")

        elif self.path == "/email":
            db("INSERT OR REPLACE INTO settings VALUES ('email', ?)", (value("email"),))
            if value("action") == "test":
                send_email("✅ Uptime Sentinel test alert",
                           "It works! Alerts will be sent to this address when a "
                           "monitored website goes DOWN or comes back UP.")
            else:
                log("Alert email saved" if value("email") else "Alert email removed")

        elif self.path == "/check":
            threading.Thread(target=lambda: [run_check(s) for s in get_sites()],
                             daemon=True).start()
            time.sleep(1)          

        elif self.path == "/toggle":
            monitoring = not monitoring
            due_at.clear()
            log("Monitoring started" if monitoring else "Monitoring stopped")

        elif self.path == "/clear":
            db("DELETE FROM checks")
            latest.clear()
            log("History cleared")

        self.send_response(303)                 
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, *args):
        pass                                    


def main():
    setup_database()
    log("Uptime Sentinel started")

   
    threading.Thread(target=monitor_loop, daemon=True).start()

    address = f"http://127.0.0.1:{PORT}"
    print(f"\nRunning on {address}   (press CTRL+C to stop)\n")
    webbrowser.open(address)

    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Server).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError:
        print(f"Port {PORT} is busy. Close the other copy, or change PORT at the top.") """


main()
