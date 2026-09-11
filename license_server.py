"""
Central Cloud License Server
============================
A 24/7 standalone Central License Management Server.
Deploy this to any cloud host (Render, Railway, PythonAnywhere, VPS) or run locally.

Features:
  1. Master Admin Dashboard: Generate, Suspend, Resume, and Delete Customer Licenses.
  2. Real-Time License API: RemoteScreenShare instances query this server to validate licenses.
  3. Live Heartbeat & Instant Kill: If you suspend a license, active viewers are kicked within 5s.
  4. Activity Logging: View all connected host IPs and customer usage in real-time.
"""

import os
import sys
import json
import time
import secrets
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from http.cookies import SimpleCookie

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "central_licenses.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("LicenseServer")

def load_data():
    data = None
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if not data:
        admin_pin = secrets.token_hex(3).upper() # e.g. A1B2C3
        default_key = f"LIC-{secrets.token_hex(4).upper()}"
        data = {
            "admin_pin": admin_pin,
            "licenses": {
                default_key: {
                    "label": "Customer 1 (Sample)",
                    "active": True,
                    "allow_control": True,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_used": "Never",
                    "active_hosts": 0
                }
            },
            "logs": []
        }
    data.setdefault("activation_requests", {})
    data.setdefault("device_licenses", {})
    data.setdefault("settings", {"offline_grace_days": 7})
    if os.environ.get("ADMIN_PIN"):
        data["admin_pin"] = os.environ.get("ADMIN_PIN").strip()
    save_data(data)
    return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

DB = load_data()
active_admin_tokens = set()

def add_log(msg, log_type="info"):
    t_str = time.strftime("%H:%M:%S")
    DB.setdefault("logs", []).insert(0, {"time": t_str, "msg": msg, "type": log_type})
    if len(DB["logs"]) > 100:
        DB["logs"] = DB["logs"][:100]
    save_data(DB)
    log.info(f"[AUDIT] {msg}")

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Central License Master Server</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; }
        body {
            margin: 0; padding: 0; background: #030712;
            color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
            min-height: 100vh; display: flex; flex-direction: column;
        }
        nav {
            background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(255,255,255,0.08);
            padding: 16px 36px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100;
        }
        .nav-brand { font-size: 1.25rem; font-weight: 800; color: #38bdf8; letter-spacing: -0.5px; display: flex; align-items: center; gap: 10px; }
        .nav-brand span.logo-badge { background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; text-transform: uppercase; font-weight: 800; }
        .container { max-width: 1280px; margin: 32px auto; padding: 0 24px; width: 100%; flex: 1; }
        
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 28px; }
        .stat-card {
            background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px; padding: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); transition: transform 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); }
        .stat-label { font-size: 0.75rem; color: #94a3b8; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
        .stat-val { font-size: 2.2rem; font-weight: 800; color: #fff; margin: 10px 0 4px; letter-spacing: -1px; }
        .stat-sub { font-size: 0.82rem; color: #64748b; font-weight: 500; }
        
        .panel {
            background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px; padding: 26px 28px; margin-bottom: 28px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }
        .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 14px; }
        .panel-title { margin: 0; font-size: 1.2rem; color: #f8fafc; font-weight: 700; display: flex; align-items: center; gap: 10px; }
        
        table { width: 100%; border-collapse: separate; border-spacing: 0; text-align: left; font-size: 0.88rem; }
        th { padding: 14px 16px; background: rgba(2, 6, 23, 0.7); color: #94a3b8; font-weight: 700; border-bottom: 1px solid rgba(255,255,255,0.08); text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.8px; }
        th:first-child { border-top-left-radius: 8px; }
        th:last-child { border-top-right-radius: 8px; }
        td { padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }
        tr:hover td { background: rgba(255,255,255,0.03); }
        code { background: #090d16; padding: 5px 10px; border-radius: 6px; color: #38bdf8; font-family: "Fira Code", monospace; border: 1px solid rgba(56,189,248,0.2); font-weight: 600; font-size: 0.84rem; }
        
        .btn {
            display: inline-flex; align-items: center; gap: 8px; padding: 10px 18px; border-radius: 8px;
            font-size: 0.85rem; font-weight: 700; cursor: pointer; border: none; transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .btn-primary { background: linear-gradient(135deg, #0284c7, #0369a1); color: #fff; }
        .btn-success { background: linear-gradient(135deg, #16a34a, #15803d); color: #fff; }
        .btn-warning { background: linear-gradient(135deg, #ea580c, #c2410c); color: #fff; }
        .btn-danger  { background: linear-gradient(135deg, #dc2626, #b91c1c); color: #fff; }
        .btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid rgba(255,255,255,0.1); }
        .btn-sm { padding: 6px 12px; font-size: 0.78rem; border-radius: 6px; }
        .btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
        
        .badge { padding: 5px 10px; border-radius: 6px; font-size: 0.72rem; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; }
        .badge-green { background: rgba(34,197,94,0.12); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }
        .badge-red   { background: rgba(239,68,68,0.12); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
        .badge-blue  { background: rgba(56,189,248,0.12); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); }
        
        input[type="text"], select {
            background: #090d16; border: 1px solid rgba(255,255,255,0.12); border-radius: 8px;
            color: #f1f5f9; padding: 10px 14px; font-size: 0.88rem; outline: none; transition: border-color 0.2s;
        }
        input[type="text"]:focus, select:focus { border-color: #38bdf8; box-shadow: 0 0 0 3px rgba(56,189,248,0.15); }
        .form-row { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
        
        .log-box {
            background: #060913; border: 1px solid rgba(255,255,255,0.06); border-radius: 10px;
            padding: 16px 18px; height: 200px; overflow-y: auto; font-family: "Fira Code", monospace; font-size: 0.82rem;
        }
        .log-line { margin-bottom: 8px; line-height: 1.5; }
        .log-time { color: #64748b; margin-right: 10px; font-weight: 500; }
        .log-info { color: #38bdf8; }
        .log-warn { color: #fbbf24; }
        .log-danger { color: #f87171; }
        
        /* Login Modal Overlay */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(3, 7, 18, 0.85); backdrop-filter: blur(16px);
            display: flex; align-items: center; justify-content: center; z-index: 1000;
            transition: opacity 0.3s;
        }
        .login-card {
            background: #0f172a; border: 1px solid rgba(255,255,255,0.12);
            border-radius: 16px; padding: 36px 32px; width: 100%; max-width: 400px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); text-align: center;
        }
        .login-card h2 { margin: 0 0 8px; font-size: 1.4rem; color: #fff; font-weight: 800; }
        .login-card p { margin: 0 0 24px; color: #94a3b8; font-size: 0.88rem; }
        .login-card input { width: 100%; text-align: center; font-size: 1.1rem; letter-spacing: 2px; padding: 12px; margin-bottom: 16px; font-weight: 700; }
        .login-card button { width: 100%; justify-content: center; padding: 12px; font-size: 0.95rem; }
        .login-error { color: #f87171; font-size: 0.82rem; margin-top: 12px; display: none; font-weight: 600; }
    </style>
</head>
<body>
    <!-- Login Modal -->
    <div id="loginModal" class="modal-overlay">
        <div class="login-card">
            <h2>🛡️ Master Admin Login</h2>
            <p>Enter your PIN to access license management</p>
            <input type="password" id="pinInput" placeholder="Enter PIN (e.g. 9B5E9B)" onkeyup="if(event.key==='Enter') submitLogin()">
            <button class="btn btn-primary" onclick="submitLogin()">Verify & Access Portal</button>
            <div id="loginError" class="login-error">Invalid PIN. Please try again.</div>
        </div>
    </div>

    <nav>
        <div class="nav-brand">
            <span>🛡️ System Master Control</span>
            <span class="logo-badge">Enterprise v3.0</span>
        </div>
        <div>
            <button class="btn btn-secondary btn-sm" onclick="loadData()">🔄 Live Refresh</button>
        </div>
    </nav>

    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Pending Requests</div>
                <div class="stat-val" id="statPending" style="color:#38bdf8;">0</div>
                <div class="stat-sub">Awaiting Admin Approval</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Remote Customers</div>
                <div class="stat-val" id="statTotal">0</div>
                <div class="stat-sub" id="statActiveRatio">0 Active | 0 Suspended</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Global Cloud Status</div>
                <div class="stat-val" style="color:#4ade80;">24/7 ONLINE</div>
                <div class="stat-sub">Central verification active</div>
            </div>
        </div>

        <!-- Active Remote Customer Management Panel -->
        <div class="panel">
            <div class="panel-header">
                <h3 class="panel-title">👥 Active Remote Customer & Device Management</h3>
                <div class="form-row">
                    <input type="text" id="devSearch" placeholder="Search Device ID, Key, PC..." onkeyup="filterDevices()" style="width:220px;">
                    <select id="devFilter" onchange="filterDevices()">
                        <option value="ALL" selected>All Devices & Statuses</option>
                        <option value="Pending">⏳ Pending Requests</option>
                        <option value="Active">🟢 Active Customers</option>
                        <option value="Suspended">⏸️ Suspended Customers</option>
                    </select>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Req ID / Device ID</th>
                        <th>Customer / Computer</th>
                        <th>OS & Version</th>
                        <th>Status</th>
                        <th>Activation Key</th>
                        <th>Activation Date / Days Active</th>
                        <th>Customer Management Actions</th>
                    </tr>
                </thead>
                <tbody id="devTbody"></tbody>
            </table>
        </div>

        <!-- Offline Grace Period & PIN Management -->
        <div class="panel">
            <div class="panel-header">
                <h3 class="panel-title">⚙️ Master Admin Settings & Security PIN</h3>
            </div>
            <div class="form-row" style="margin-bottom:14px;">
                <span style="color:#94a3b8; font-size:0.88rem;">Master Admin PIN:</span>
                <input type="text" id="newPin" placeholder="New PIN (e.g. 9B5E9B)" style="width:180px;">
                <button class="btn btn-secondary" onclick="updatePin()">Change PIN</button>
            </div>
            <div class="form-row">
                <span style="color:#94a3b8; font-size:0.88rem;">Offline Grace Period (Days):</span>
                <input type="number" id="graceInput" placeholder="7" min="1" max="90" style="width:100px; background:#090d16; border:1px solid rgba(255,255,255,0.12); border-radius:8px; color:#f1f5f9; padding:10px 14px;">
                <button class="btn btn-secondary" onclick="updateGrace()">Save Grace Period</button>
            </div>
        </div>

        <!-- Real-Time Activity Log -->
        <div class="panel">
            <div class="panel-header">
                <h3 class="panel-title">📜 Central Security & License Event Log</h3>
            </div>
            <div class="log-box" id="logBox"></div>
        </div>
    </div>

    <script>
        let isAuthenticating = false;
        let cachedDeviceRequests = {};
        let cachedDeviceLicenses = {};

        async function fetchAdmin(url, opts = {}) {
            const tok = localStorage.getItem('master_admin_token') || '';
            opts.headers = opts.headers || {};
            if (tok) opts.headers['X-Admin-Token'] = tok;
            opts.credentials = 'same-origin';
            return fetch(url, opts);
        }

        async function submitLogin() {
            const pin = document.getElementById('pinInput').value.trim();
            if (!pin) return;
            const errDiv = document.getElementById('loginError');
            errDiv.style.display = 'none';

            try {
                const loginRes = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({pin})
                });
                const d = await loginRes.json();
                if (d.status === 'ok' && d.token) {
                    localStorage.setItem('master_admin_token', d.token);
                    document.getElementById('loginModal').style.display = 'none';
                    isAuthenticating = false;
                    loadData();
                } else {
                    errDiv.innerText = 'Invalid PIN. Please try again.';
                    errDiv.style.display = 'block';
                }
            } catch(e) {
                errDiv.innerText = 'Connection error. Please try again.';
                errDiv.style.display = 'block';
            }
        }

        async function loadData() {
            if (isAuthenticating) return;
            try {
                const res = await fetchAdmin('/api/admin/data');
                if (res.status === 401) {
                    isAuthenticating = true;
                    document.getElementById('loginModal').style.display = 'flex';
                    return;
                }
                document.getElementById('loginModal').style.display = 'none';
                const data = await res.json();

                cachedDeviceRequests = data.activation_requests || {};
                cachedDeviceLicenses = data.device_licenses || {};

                // Render Settings safely
                const graceEl = document.getElementById('graceInput');
                if (graceEl && data.settings && data.settings.offline_grace_days) {
                    graceEl.value = data.settings.offline_grace_days;
                }

                // Render Stats
                const allReqs = Object.values(cachedDeviceRequests);
                const allLics = Object.values(cachedDeviceLicenses);
                let active = 0, suspended = 0, pending = 0;
                
                const uniqueDevices = new Set();
                allReqs.forEach(r => { if (r.device_id) uniqueDevices.add(r.device_id); });
                allLics.forEach(l => { if (l.device_id) uniqueDevices.add(l.device_id); });

                allReqs.forEach(r => {
                    if (r.status === 'Active') active++;
                    else if (r.status === 'Suspended') suspended++;
                    else if (r.status === 'Pending') pending++;
                });

                const statPen = document.getElementById('statPending');
                if (statPen) statPen.innerText = pending;
                const statTot = document.getElementById('statTotal');
                if (statTot) statTot.innerText = uniqueDevices.size || allReqs.length;
                const statRatio = document.getElementById('statActiveRatio');
                if (statRatio) statRatio.innerText = `${active} Active | ${suspended} Suspended`;

                // Render Devices
                filterDevices();

                // Render Logs
                const logBox = document.getElementById('logBox');
                if (logBox) {
                    logBox.innerHTML = (data.logs || []).map(l => `
                        <div class="log-line">
                            <span class="log-time">[${l.time}]</span>
                            <span class="log-${l.type}">${l.msg}</span>
                        </div>
                    `).join('');
                }

            } catch(e) {
                console.error("Load error", e);
            }
        }

        async function updateGrace() {
            const val = parseInt(document.getElementById('graceInput').value);
            if (isNaN(val) || val < 1) { alert("Grace period must be at least 1 day."); return; }
            await fetchAdmin('/api/admin/device/set_grace', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({offline_grace_days: val})
            });
            alert("Offline Grace Period updated to " + val + " days!");
            loadData();
        }

        function getDaysActive(dateStr) {
            if (!dateStr || dateStr === 'N/A') return 'N/A';
            try {
                const t = new Date(dateStr.replace(' ', 'T')).getTime();
                if (isNaN(t)) return dateStr;
                const diffDays = Math.floor((Date.now() - t) / 86400000);
                if (diffDays <= 0) return `${dateStr} (< 1 day active)`;
                return `${dateStr} (${diffDays} day${diffDays > 1 ? 's' : ''} active)`;
            } catch(e) {
                return dateStr;
            }
        }

        function filterDevices() {
            const query = (document.getElementById('devSearch').value || '').toLowerCase();
            const statusFilter = document.getElementById('devFilter').value;
            const tbody = document.getElementById('devTbody');

            const allReqs = Object.values(cachedDeviceRequests);
            if (!allReqs.length) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:24px;">No activation requests found.</td></tr>`;
                return;
            }

            const filtered = allReqs.filter(r => {
                const matchesQuery = !query || 
                    (r.device_id || '').toLowerCase().includes(query) ||
                    (r.request_id || '').toLowerCase().includes(query) ||
                    (r.computer_name || '').toLowerCase().includes(query) ||
                    (r.user_name || '').toLowerCase().includes(query) ||
                    (r.activation_key || '').toLowerCase().includes(query);

                const matchesStatus = (statusFilter === 'ALL') || (r.status === statusFilter);
                return matchesQuery && matchesStatus;
            });

            if (!filtered.length) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:24px;">No devices matching filter criteria.</td></tr>`;
                return;
            }

            tbody.innerHTML = filtered.map(r => {
                let badge = `<span class="badge badge-blue">⏳ ${r.status}</span>`;
                if (r.status === 'Approved') badge = `<span class="badge badge-green">🟡 Approved</span>`;
                else if (r.status === 'Active') badge = `<span class="badge badge-green">🟢 ACTIVE</span>`;
                else if (r.status === 'Suspended') badge = `<span class="badge badge-red">⏸️ SUSPENDED</span>`;
                else if (r.status === 'Rejected') badge = `<span class="badge badge-red">⛔ Rejected</span>`;

                let actions = '';
                if (r.status === 'Pending' || r.status === 'Rejected') {
                    actions += `<button class="btn btn-success btn-sm" onclick="approveDevice('${r.request_id}', '${r.device_id}')">✅ Approve & Key</button> `;
                    actions += `<button class="btn btn-danger btn-sm" onclick="rejectDevice('${r.request_id}')">❌ Reject</button>`;
                } else {
                    if (r.status === 'Suspended') {
                        actions += `<button class="btn btn-success btn-sm" onclick="restoreDevice('${r.device_id}', '${r.activation_key}')">🟢 Restore Access</button> `;
                    } else {
                        actions += `<button class="btn btn-warning btn-sm" onclick="suspendDevice('${r.device_id}', '${r.activation_key}')">⏸️ Suspend</button> `;
                    }
                    actions += `<button class="btn btn-secondary btn-sm" onclick="resetBinding('${r.device_id}', '${r.activation_key}')">🔄 Reset Binding</button> `;
                    actions += `<button class="btn btn-danger btn-sm" onclick="removeDevice('${r.device_id}', '${r.activation_key}')">🗑️ Remove</button>`;
                }

                const keyDisplay = r.activation_key ? `<code>${r.activation_key}</code> <span class="copy-btn" onclick="copyKey('${r.activation_key}')">📋</span>` : `<em style="color:#64748b;">Not generated</em>`;
                const dateDisplay = getDaysActive(r.created_at || r.last_seen_at);

                return `
                    <tr>
                        <td>
                            <div><strong style="color:#38bdf8;">${r.request_id}</strong></div>
                            <code>${r.device_id}</code> <span class="copy-btn" onclick="copyKey('${r.device_id}')">📋</span>
                        </td>
                        <td>
                            <div><strong>${r.user_name || 'Buyer'}</strong></div>
                            <small style="color:#94a3b8;">💻 ${r.computer_name || 'Unknown'}</small>
                        </td>
                        <td><small style="color:#cbd5e1;">${r.os || 'Windows'} (v${r.app_version || '2.5'})</small></td>
                        <td>${badge}</td>
                        <td>${keyDisplay}</td>
                        <td>
                            <div><small style="color:#38bdf8;">${dateDisplay}</small></div>
                            <div><small style="color:#64748b;">Last Seen: ${r.last_seen_at || 'N/A'}</small></div>
                        </td>
                        <td><div style="display:flex; gap:4px; flex-wrap:wrap;">${actions}</div></td>
                    </tr>
                `;
            }).join('');
        }

        async function approveDevice(reqId, devId) {
            const res = await fetchAdmin('/api/admin/device/approve', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({request_id: reqId, device_id: devId})
            });
            const d = await res.json();
            if (d.status === 'ok') {
                alert(`Device Approved successfully!\nGenerated Activation Key: ${d.activation_key}\nSend this key to the buyer.`);
                loadData();
            } else {
                alert("Error approving device: " + (d.message || "Unknown error"));
            }
        }

        async function rejectDevice(reqId) {
            if (!confirm("Reject this device activation request?")) return;
            await fetchAdmin('/api/admin/device/reject', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({request_id: reqId})
            });
            loadData();
        }

        async function suspendDevice(devId, actKey) {
            await fetchAdmin('/api/admin/device/suspend', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_id: devId, activation_key: actKey})
            });
            loadData();
        }

        async function restoreDevice(devId, actKey) {
            await fetchAdmin('/api/admin/device/restore', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_id: devId, activation_key: actKey})
            });
            loadData();
        }

        async function removeDevice(devId, actKey) {
            if (!confirm(`Remove customer device ${devId} permanently? This will safely clean up all records for this customer.`)) return;
            await fetchAdmin('/api/admin/device/remove', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_id: devId, activation_key: actKey})
            });
            loadData();
        }

        async function resetBinding(devId, actKey) {
            if (!confirm(`Reset Device Binding for key ${actKey}? This allows transferring the license to a new computer.`)) return;
            await fetchAdmin('/api/admin/device/reset_binding', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_id: devId, activation_key: actKey})
            });
            alert("Device binding reset! The buyer can now activate this key on a new computer.");
            loadData();
        }

        function copyKey(txt) {
            navigator.clipboard.writeText(txt);
        }

        async function updatePin() {
            const pin = document.getElementById('newPin').value.trim();
            if (!pin || pin.length < 4) { alert("PIN must be at least 4 chars."); return; }
            await fetchAdmin('/api/admin/change_pin', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({pin})
            });
            alert("Master Admin PIN updated!");
            document.getElementById('newPin').value = '';
            loadData();
        }

        function copyKey(key) {
            navigator.clipboard.writeText(key).then(() => alert("Copied: " + key));
        }

        loadData();
        setInterval(loadData, 3000);
    </script>
</body>
</html>
"""

class LicenseHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def is_admin(self):
        # 1. Check custom Header (for localStorage persistence)
        header_tok = self.headers.get('X-Admin-Token')
        if header_tok and header_tok in active_admin_tokens:
            return True

        # 2. Check Cookie
        cookie = self.headers.get('Cookie')
        if cookie:
            c = SimpleCookie(cookie)
            tok = c.get('admin_token')
            if tok and tok.value in active_admin_tokens:
                return True
        return False

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8')) if body else {}

            # --- PUBLIC API FOR HOST COMPUTERS ---
            if self.path == "/api/verify":
                key = data.get("license", "").strip().upper()
                host_ip = self.client_address[0]
                hostname = data.get("hostname", "Unknown Host")
                public_url = data.get("public_url", "")
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                
                # Check DB["device_licenses"] first, then DB["licenses"]
                lic = None
                for d_k, d_lic in DB.get("device_licenses", {}).items():
                    if d_k == key or d_lic.get("activation_key", "").upper() == key:
                        lic = d_lic
                        break

                if not lic:
                    lic = DB.get("licenses", {}).get(key)

                # Never auto-approve unknown keys as active! Put in activation_requests as Pending.
                if not lic:
                    dev_id = f"DEV-{key}"
                    requests = DB.setdefault("activation_requests", {})
                    req_found = False
                    for r_id, req in requests.items():
                        if req.get("activation_key") == key or req.get("device_id") == dev_id:
                            req_found = True
                            req["last_seen_at"] = now_str
                            break
                    if not req_found:
                        r_id = f"REQ-{secrets.token_hex(4).upper()}"
                        requests[r_id] = {
                            "request_id": r_id,
                            "device_id": dev_id,
                            "user_name": f"Viewer ({host_ip})",
                            "computer_name": hostname,
                            "os": "Windows",
                            "app_version": "2.5.0",
                            "status": "Pending",
                            "activation_key": key,
                            "created_at": now_str,
                            "last_seen_at": now_str
                        }
                        save_data(DB)
                        add_log(f"NEW Access Request: Viewer [{key}] ({hostname}) - Pending Approval", "info")

                    self._respond(200, "application/json", b'{"valid":false,"active":false,"status":"Pending","reason":"Pending Admin Approval"}')
                    return

                if not lic.get("active", True) or lic.get("status") in ("Suspended", "Revoked"):
                    add_log(f"Verification BLOCKED: Suspended key '{key}' from Host {hostname} ({host_ip})", "warn")
                    self._respond(403, "application/json", b'{"valid":false,"active":false,"status":"Suspended","reason":"License is Suspended by Admin"}')
                    return

                lic["last_used"] = now_str
                lic["last_host"] = f"{hostname} ({host_ip})"
                lic["last_url"] = public_url
                save_data(DB)
                add_log(f"License VALIDATED: {lic.get('label', 'Device License')} ({key}) connected on {hostname} [{public_url}]", "info")
                self._respond(200, "application/json", json.dumps({
                    "valid": True,
                    "active": True,
                    "status": "Active",
                    "allow_control": lic.get("allow_control", True),
                    "label": lic.get("label", "Device License")
                }).encode())
                return

            # Heartbeat check from host instances (every 5s)
            elif self.path == "/api/heartbeat":
                key = data.get("license", "").strip().upper()
                host_ip = self.client_address[0]
                hostname = data.get("hostname", "Unknown Host")
                public_url = data.get("public_url", "")
                client_ip = data.get("client_ip", "")

                lic = None
                for d_k, d_lic in DB.get("device_licenses", {}).items():
                    if d_k == key or d_lic.get("activation_key", "").upper() == key:
                        lic = d_lic
                        break
                if not lic:
                    lic = DB.get("licenses", {}).get(key)

                if not lic or not lic.get("active", True) or lic.get("status") in ("Suspended", "Revoked"):
                    # Signal host to kill active session immediately!
                    self._respond(200, "application/json", b'{"action":"terminate","reason":"License revoked or suspended by Admin"}')
                    return

                # Update live session metadata
                lic["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
                lic["last_host"] = f"{hostname} ({host_ip})"
                lic["last_url"] = public_url
                lic["active_client_ip"] = client_ip
                save_data(DB)

                self._respond(200, "application/json", json.dumps({
                    "action": "continue",
                    "allow_control": lic.get("allow_control", True)
                }).encode())
                return

            # --- DEVICE ACTIVATION & LICENSE AUTHORIZATION API ---
            elif self.path == "/api/license/request_activation":
                dev_id = data.get("device_id", "").strip().upper()
                act_key = data.get("activation_key", "").strip().upper() or data.get("license", "").strip().upper()
                comp_name = data.get("computer_name", "Unknown Device")
                os_info = data.get("os", "Windows")
                app_ver = data.get("app_version", "2.5.0")
                user_name = data.get("user_name", "Buyer")
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")

                if not dev_id and not act_key:
                    self._respond(400, "application/json", b'{"status":"error","message":"Missing device_id or key"}')
                    return

                if not dev_id:
                    dev_id = f"DEV-{act_key}"

                requests = DB.setdefault("activation_requests", {})
                req_info = None
                for r_id, req in requests.items():
                    if req.get("device_id") == dev_id or (act_key and req.get("activation_key") == act_key):
                        req_info = req
                        req["last_seen_at"] = now_str
                        req["computer_name"] = comp_name
                        if act_key:
                            req["activation_key"] = act_key
                        if user_name and user_name != "Buyer":
                            req["user_name"] = user_name
                        break

                # Check if this device/key is already approved by admin in device_licenses
                dev_lics = DB.get("device_licenses", {})
                is_already_approved = False
                for k, lic in dev_lics.items():
                    if lic.get("device_id") == dev_id or (act_key and (k == act_key or lic.get("activation_key") == act_key)):
                        if lic.get("active") is True and lic.get("status") == "Active":
                            is_already_approved = True
                            break

                if not req_info:
                    r_id = f"REQ-{secrets.token_hex(4).upper()}"
                    req_info = {
                        "request_id": r_id,
                        "device_id": dev_id,
                        "user_name": user_name,
                        "computer_name": comp_name,
                        "os": os_info,
                        "app_version": app_ver,
                        "status": "Active" if is_already_approved else "Pending",
                        "activation_key": act_key,
                        "created_at": now_str,
                        "last_seen_at": now_str
                    }
                    requests[r_id] = req_info
                    add_log(f"NEW Access Request: {user_name} [{dev_id}] Key: {act_key} - Status: {req_info['status']}", "info")
                else:
                    if not is_already_approved and req_info.get("status") not in ("Suspended", "Rejected"):
                        req_info["status"] = "Pending"

                save_data(DB)
                self._respond(200, "application/json", json.dumps({
                    "status": "ok",
                    "request_id": req_info["request_id"],
                    "activation_status": req_info["status"],
                    "activation_key": req_info.get("activation_key", ""),
                    "offline_grace_days": DB.get("settings", {}).get("offline_grace_days", 7)
                }).encode())
                return

            elif self.path == "/api/license/verify_device":
                dev_id = data.get("device_id", "").strip().upper()
                act_key = data.get("activation_key", "").strip().upper() or data.get("license", "").strip().upper()
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")

                if not dev_id and not act_key:
                    self._respond(400, "application/json", b'{"status":"error","message":"Missing device_id or key"}')
                    return

                dev_lics = DB.get("device_licenses", {})
                reqs = DB.get("activation_requests", {})
                grace_days = DB.get("settings", {}).get("offline_grace_days", 7)

                matched_lic = None
                for key, lic in dev_lics.items():
                    if (dev_id and lic.get("device_id") == dev_id) or (act_key and (key == act_key or lic.get("activation_key") == act_key)):
                        matched_lic = lic
                        break

                if matched_lic:
                    status = matched_lic.get("status", "Active")
                    if status == "Suspended":
                        self._respond(200, "application/json", json.dumps({
                            "status": "Suspended",
                            "message": "Your license is suspended. Please contact the administrator."
                        }).encode())
                        return
                    elif status == "Revoked":
                        self._respond(200, "application/json", json.dumps({
                            "status": "Revoked",
                            "message": "This device has been revoked by the administrator."
                        }).encode())
                        return

                    matched_lic["last_verified_at"] = now_str
                    save_data(DB)
                    self._respond(200, "application/json", json.dumps({
                        "status": "Active",
                        "allow_control": matched_lic.get("allow_control", True),
                        "activation_key": matched_lic.get("activation_key", ""),
                        "offline_grace_days": grace_days,
                        "server_time": time.time()
                    }).encode())
                    return

                req_status = "Pending"
                req_msg = "Your access request is pending Admin approval."
                req_info = None
                for r_id, req in reqs.items():
                    if (dev_id and req.get("device_id") == dev_id) or (act_key and req.get("activation_key") == act_key):
                        req_info = req
                        req_status = req.get("status", "Pending")
                        req["last_seen_at"] = now_str
                        if req_status in ("Approved", "Active"):
                            act_k = req.get("activation_key", act_key)
                            req["status"] = "Active"
                            save_data(DB)
                            self._respond(200, "application/json", json.dumps({
                                "status": "Active",
                                "allow_control": True,
                                "activation_key": act_k,
                                "offline_grace_days": grace_days,
                                "server_time": time.time()
                            }).encode())
                            return
                        elif req_status == "Rejected":
                            req_msg = "Activation request was rejected by administrator."
                            self._respond(200, "application/json", json.dumps({
                                "status": "Rejected",
                                "message": req_msg
                            }).encode())
                            return
                        elif req_status == "Suspended":
                            self._respond(200, "application/json", json.dumps({
                                "status": "Suspended",
                                "message": "License suspended by administrator."
                            }).encode())
                            return
                        break

                if req_info:
                    self._respond(200, "application/json", json.dumps({
                        "status": req_status,
                        "message": req_msg
                    }).encode())
                    return
                else:
                    r_id = f"REQ-{secrets.token_hex(4).upper()}"
                    comp_name = data.get("computer_name", "Unknown Device")
                    user_name = data.get("user_name", f"Viewer ({dev_id})")
                    req_info = {
                        "request_id": r_id,
                        "device_id": dev_id,
                        "user_name": user_name,
                        "computer_name": comp_name,
                        "os": data.get("os", "Windows"),
                        "app_version": data.get("app_version", "2.5.0"),
                        "status": "Pending",
                        "activation_key": act_key,
                        "created_at": now_str,
                        "last_seen_at": now_str
                    }
                    reqs[r_id] = req_info
                    add_log(f"NEW Access Request: {user_name} on {comp_name} [{dev_id}] Key: {act_key}", "info")
                    save_data(DB)
                    self._respond(200, "application/json", json.dumps({
                        "status": "Pending",
                        "message": req_msg,
                        "offline_grace_days": grace_days
                    }).encode())
                    return

            elif self.path == "/api/license/submit_key":
                dev_id = data.get("device_id", "").strip().upper()
                act_key = data.get("activation_key", "").strip().upper()
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")

                dev_lics = DB.setdefault("device_licenses", {})
                reqs = DB.setdefault("activation_requests", {})
                lics = DB.setdefault("licenses", {})

                lic_match = None
                # 1. Lookup in device_licenses
                for l_id, lic in dev_lics.items():
                    if lic.get("activation_key", "").upper() == act_key:
                        lic_match = lic
                        break

                # 2. Fallback lookup in DB["licenses"]
                if not lic_match and act_key in lics:
                    lic_match = lics[act_key]
                    lic_match["activation_key"] = act_key

                if not lic_match and dev_id:
                    for r_id, req in reqs.items():
                        if req.get("device_id") == dev_id and req.get("status") in ("Approved", "Active"):
                            a_key = req.get("activation_key") or f"LIC-{secrets.token_hex(3).upper()}"
                            req["activation_key"] = a_key
                            req["status"] = "Active"
                            lic_match = {
                                "license_id": f"LIC-DEV-{secrets.token_hex(3).upper()}",
                                "activation_key": a_key,
                                "device_id": dev_id,
                                "status": "Active",
                                "active": True,
                                "allow_control": True,
                                "created_at": now_str,
                                "activated_at": now_str
                            }
                            dev_lics[a_key] = lic_match
                            lics[a_key] = lic_match
                            break

                if not lic_match:
                    self._respond(400, "application/json", json.dumps({
                        "status": "error",
                        "message": "Invalid Activation Key. Contact Admin for approved Key."
                    }).encode())
                    return

                bound_dev = lic_match.get("device_id")
                if bound_dev and bound_dev != dev_id:
                    self._respond(403, "application/json", json.dumps({
                        "status": "error",
                        "message": "This Activation Key was already bound to another device."
                    }).encode())
                    return

                lic_match["device_id"] = dev_id
                lic_match["status"] = "Active"
                lic_match["active"] = True
                lic_match["activated_at"] = now_str
                lic_match["last_verified_at"] = now_str

                act_k = lic_match.get("activation_key", act_key)
                dev_lics[act_k] = lic_match
                lics[act_k] = lic_match

                for r_id, req in reqs.items():
                    if req.get("device_id") == dev_id or req.get("activation_key") == act_k:
                        req["status"] = "Active"
                        req["device_id"] = dev_id
                        req["activation_key"] = act_k

                save_data(DB)
                add_log(f"Device ACTIVATED successfully: {dev_id} with key {act_k}", "info")
                self._respond(200, "application/json", json.dumps({
                    "status": "Active",
                    "activation_key": act_k,
                    "message": "Activation successful! Unlocking application...",
                    "offline_grace_days": DB.get("settings", {}).get("offline_grace_days", 7)
                }).encode())
                return

            # --- ADMIN ACTIONS ---
            elif self.path == "/api/admin/login":
                pin = data.get("pin", "").strip().upper()
                if pin == DB.get("admin_pin", "").upper():
                    tok = secrets.token_hex(16)
                    active_admin_tokens.add(tok)
                    self._send_cookie_resp(tok, {"status": "ok", "token": tok})
                    return
                self._respond(401, "application/json", b'{"status":"error","message":"Invalid Admin PIN"}')
                return

            if not self.is_admin():
                self._respond(401, "application/json", b'{"error":"Admin required"}')
                return

            if self.path == "/api/admin/device/approve":
                req_id = data.get("request_id")
                reqs = DB.get("activation_requests", {})
                req = reqs.get(req_id)
                if not req:
                    dev_id = data.get("device_id")
                    req = next((r for r in reqs.values() if r.get("device_id") == dev_id), None)

                if not req:
                    self._respond(404, "application/json", b'{"error":"Request not found"}')
                    return

                dev_id = req["device_id"]
                act_key = req.get("activation_key") or f"LIC-{secrets.token_hex(3).upper()}"
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")

                req["status"] = "Active"
                req["activation_key"] = act_key

                lic_entry = {
                    "license_id": f"LIC-DEV-{secrets.token_hex(3).upper()}",
                    "activation_key": act_key,
                    "device_id": dev_id,
                    "status": "Active",
                    "active": True,
                    "allow_control": True,
                    "created_at": now_str,
                    "activated_at": now_str,
                    "last_verified_at": now_str,
                    "label": f"{req.get('user_name', 'Buyer')} ({req.get('computer_name', 'PC')})",
                    "computer_name": req.get("computer_name", "")
                }
                DB.setdefault("device_licenses", {})[act_key] = lic_entry
                DB.setdefault("licenses", {})[act_key] = lic_entry

                save_data(DB)
                add_log(f"Admin APPROVED device {dev_id} ({req.get('computer_name')}). Key: {act_key}", "info")
                self._respond(200, "application/json", json.dumps({"status": "ok", "activation_key": act_key}).encode())
                return

            elif self.path == "/api/admin/device/reject":
                req_id = data.get("request_id")
                reqs = DB.get("activation_requests", {})
                req = reqs.get(req_id)
                if req:
                    req["status"] = "Rejected"
                    save_data(DB)
                    add_log(f"Admin REJECTED activation request {req_id} [{req.get('device_id')}]", "warn")
                self._respond(200, "application/json", b'{"status":"ok"}')
                return

            elif self.path == "/api/admin/device/suspend":
                dev_id = data.get("device_id")
                act_key = data.get("activation_key")
                for key, lic in DB.get("device_licenses", {}).items():
                    if lic.get("device_id") == dev_id or (act_key and lic.get("activation_key") == act_key):
                        lic["status"] = "Suspended"
                        lic["active"] = False
                for req in DB.get("activation_requests", {}).values():
                    if req.get("device_id") == dev_id or (act_key and req.get("activation_key") == act_key):
                        req["status"] = "Suspended"
                save_data(DB)
                add_log(f"Admin SUSPENDED customer access for device {dev_id}", "warn")
                self._respond(200, "application/json", b'{"status":"ok"}')
                return

            elif self.path in ("/api/admin/device/restore", "/api/admin/device/reactivate"):
                dev_id = data.get("device_id")
                act_key = data.get("activation_key")
                for key, lic in DB.get("device_licenses", {}).items():
                    if lic.get("device_id") == dev_id or (act_key and lic.get("activation_key") == act_key):
                        lic["status"] = "Active"
                        lic["active"] = True
                for req in DB.get("activation_requests", {}).values():
                    if req.get("device_id") == dev_id or (act_key and req.get("activation_key") == act_key):
                        req["status"] = "Active"
                save_data(DB)
                add_log(f"Admin RESTORED customer access for device {dev_id}", "info")
                self._respond(200, "application/json", b'{"status":"ok"}')
                return

            elif self.path in ("/api/admin/device/remove", "/api/admin/device/revoke"):
                dev_id = data.get("device_id")
                act_key = data.get("activation_key")
                
                dev_lics = DB.setdefault("device_licenses", {})
                lics = DB.setdefault("licenses", {})
                reqs = DB.setdefault("activation_requests", {})

                keys_to_del = [k for k, v in dev_lics.items() if v.get("device_id") == dev_id or (act_key and k == act_key)]
                for k in keys_to_del:
                    del dev_lics[k]
                    if k in lics:
                        del lics[k]

                req_ids_to_del = [r_id for r_id, req in reqs.items() if req.get("device_id") == dev_id or (act_key and req.get("activation_key") == act_key)]
                for r_id in req_ids_to_del:
                    del reqs[r_id]

                save_data(DB)
                add_log(f"Admin REMOVED customer record for device {dev_id}", "warn")
                self._respond(200, "application/json", b'{"status":"ok"}')
                return

            elif self.path == "/api/admin/device/reset_binding":
                dev_id = data.get("device_id")
                act_key = data.get("activation_key")
                for key, lic in DB.get("device_licenses", {}).items():
                    if lic.get("activation_key") == act_key or lic.get("device_id") == dev_id:
                        old_dev = lic.get("device_id")
                        lic["device_id"] = ""
                        lic["status"] = "Approved"
                        add_log(f"Admin RESET DEVICE BINDING for Key {key} (Unbound from {old_dev})", "warn")
                save_data(DB)
                self._respond(200, "application/json", b'{"status":"ok"}')
                return

            elif self.path == "/api/admin/device/set_grace":
                days = int(data.get("offline_grace_days", 7))
                DB.setdefault("settings", {})["offline_grace_days"] = max(1, days)
                save_data(DB)
                add_log(f"Admin updated offline grace period to {days} days", "info")
                self._respond(200, "application/json", b'{"status":"ok"}')
                return

            if self.path == "/api/admin/create":
                new_k = f"LIC-{secrets.token_hex(4).upper()}"
                label = data.get("label", "Customer License")
                ctrl = bool(data.get("allow_control", True))
                DB["licenses"][new_k] = {
                    "label": label,
                    "active": True,
                    "allow_control": ctrl,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_used": "Never"
                }
                save_data(DB)
                add_log(f"Admin issued new license: {label} ({new_k})", "info")
                self._respond(200, "application/json", json.dumps({"status":"ok","key":new_k}).encode())

            elif self.path == "/api/admin/toggle":
                k = data.get("key")
                act = bool(data.get("active", True))
                if k in DB["licenses"]:
                    DB["licenses"][k]["active"] = act
                    save_data(DB)
                    status_str = "ACTIVATED" if act else "SUSPENDED / STOPPED"
                    add_log(f"Admin {status_str} license: {k}", "warn" if not act else "info")
                self._respond(200, "application/json", b'{"status":"ok"}')

            elif self.path == "/api/admin/perm":
                k = data.get("key")
                ctrl = bool(data.get("allow_control", True))
                if k in DB["licenses"]:
                    DB["licenses"][k]["allow_control"] = ctrl
                    save_data(DB)
                    add_log(f"Admin changed permission for {k} to Control={ctrl}", "info")
                self._respond(200, "application/json", b'{"status":"ok"}')

            elif self.path == "/api/admin/revoke":
                k = data.get("key")
                if k in DB["licenses"]:
                    del DB["licenses"][k]
                    save_data(DB)
                    add_log(f"Admin DELETED license {k}", "danger")
                self._respond(200, "application/json", b'{"status":"ok"}')

            elif self.path == "/api/admin/change_pin":
                new_p = data.get("pin", "").strip().upper()
                if len(new_p) >= 4:
                    DB["admin_pin"] = new_p
                    save_data(DB)
                    add_log("Master Admin PIN updated.", "info")
                    self._respond(200, "application/json", b'{"status":"ok"}')

        except Exception as e:
            log.error(f"POST Error {self.path}: {e}")
            self._respond(500, "application/json", json.dumps({"error":str(e)}).encode())

    def do_GET(self):
        try:
            if self.path == "/api/admin/data":
                if not self.is_admin():
                    self._respond(401, "application/json", b'{"error":"Admin required"}')
                    return
                self._respond(200, "application/json", json.dumps({
                    "licenses": DB["licenses"],
                    "activation_requests": DB.get("activation_requests", {}),
                    "device_licenses": DB.get("device_licenses", {}),
                    "settings": DB.get("settings", {"offline_grace_days": 7}),
                    "logs": DB.get("logs", [])
                }).encode())
                return
            elif self.path.startswith("/api/"):
                self._respond(200, "application/json", b'{"status":"ok","message":"Central Licensing Master Server is ONLINE. Open /admin to access Admin Portal."}')
                return
            else:
                self._respond(200, "text/html; charset=utf-8", ADMIN_HTML.encode())
        except Exception as e:
            log.error(f"GET Error: {e}")

    def _send_cookie_resp(self, token, resp_dict):
        body = json.dumps(resp_dict).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", f"admin_token={token}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

import subprocess
import threading
import re

def start_license_server_tunnel(port):
    cf = os.path.join(BASE_DIR, "cloudflared.exe")
    if not os.path.isfile(cf):
        cf = os.path.join(BASE_DIR, "TunnelService.exe")
    if not os.path.isfile(cf):
        log.info(f"Local Central License Server running on http://127.0.0.1:{port}")
        return

    flags = 0x08000000 if sys.platform == "win32" else 0
    cf_log = os.path.join(BASE_DIR, "cf_admin_tunnel.log")
    if os.path.exists(cf_log):
        try:
            os.remove(cf_log)
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            [cf, "tunnel", "--url", f"http://127.0.0.1:{port}", "--logfile", cf_log],
            creationflags=flags
        )
    except Exception as e:
        log.error(f"Failed to spawn admin tunnel: {e}")
        return

    public_url = ""
    deadline = time.time() + 25
    while time.time() < deadline:
        if proc.poll() is not None: break
        if os.path.exists(cf_log):
            try:
                with open(cf_log, "r", encoding="utf-8", errors="ignore") as lf:
                    content = lf.read()
                    m = re.search(r"https://([a-zA-Z0-9\-]+)\.trycloudflare\.com", content)
                    if m and m.group(1).lower() != "api":
                        public_url = m.group(0)
                        break
            except Exception:
                pass
        time.sleep(0.4)

    if public_url:
        log.info(f"==================================================")
        log.info(f"🛡️ CENTRAL MASTER LICENSE SERVER PUBLIC CLOUD ONLINE")
        log.info(f"👉 Master Admin PIN: {DB['admin_pin']}")
        log.info(f"👉 Local Admin Link: http://localhost:{port}")
        log.info(f"🌐 PUBLIC CLOUD URL: {public_url}")
        log.info(f"==================================================")

        # Update server_config.json with public URL
        cfg_path = os.path.join(BASE_DIR, "server_config.json")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"central_server_url": public_url}, f, indent=4)
            log.info(f"Updated {cfg_path} with public URL: {public_url}")
            
            # Copy to dist if exists
            dist_dir = os.path.join(BASE_DIR, "dist", "SystemHostService")
            dist_cfg = os.path.join(dist_dir, "server_config.json")
            if os.path.exists(dist_dir):
                with open(dist_cfg, "w", encoding="utf-8") as f:
                    json.dump({"central_server_url": public_url}, f, indent=4)
            # Update portable zip if present
            zip_parent = os.path.dirname(BASE_DIR)
            portable_zip = os.path.join(zip_parent, "SystemHost_Portable.zip")
            if os.path.exists(portable_zip) and os.path.exists(dist_dir):
                try:
                    import zipfile
                    with zipfile.ZipFile(portable_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                        for root, _, files in os.walk(dist_dir):
                            for fn in files:
                                fp = os.path.join(root, fn)
                                arcname = os.path.relpath(fp, dist_dir)
                                zf.write(fp, arcname)
                    log.info(f"Updated {portable_zip} with new public URL.")
                except Exception as ze:
                    log.warning(f"Could not re-pack portable zip: {ze}")
        except Exception as e:
            log.warning(f"Could not update server_config.json: {e}")
    else:
        log.info(f"Central License Server running locally on http://127.0.0.1:{port}")

def main():
    port = int(os.environ.get("PORT", 8888))
    log.info(f"Central License Master Server starting on port {port}...")
    log.info(f"Master Admin PIN: {DB['admin_pin']}")

    threading.Thread(target=start_license_server_tunnel, args=(port,), daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", port), LicenseHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")

if __name__ == "__main__":
    main()
