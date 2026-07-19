/**
 * public/js/app.js
 * Main frontend application logic for the ADC Monitoring Dashboard.
 * Handles API requests, dynamic UI rendering, role-based visibility, and Socket.IO.
 */

'use strict';

// ---------------------------------------------------------------------------
// Main Application Namespace
// ---------------------------------------------------------------------------
const App = {
  socket: null,
  devices: [],
  user: null,
  currentView: 'dashboard',
  currentSort: { NVR: 'name_asc', CAM: 'name_asc', ATM: 'name_asc' },
  deleteTargetId: null,

  // Initialize the application
  async init() {
    console.log('[App] Initializing dashboard...');
    this.startClock();
    this.startUptimeCounter();
    
    // 1. Verify session
    const authenticated = await this.checkSession();
    if (!authenticated) return;

    // 2. Initialize Socket.IO
    this.initSocket();

    // 3. Setup Navigation & UI event listeners
    this.setupEventListeners();
    this.applyRoleCustomizations();

    // 4. Load initial dashboard data
    await this.refreshData();
  },

  // -------------------------------------------------------------------------
  // Session & Authentication
  // -------------------------------------------------------------------------
  async checkSession() {
    try {
      const res = await fetch('/api/auth/me');
      if (res.status === 401) {
        window.location.href = '/login.html';
        return false;
      }
      const result = await res.json();
      if (result.success) {
        this.user = result.data;
        return true;
      }
    } catch (err) {
      console.error('[App] Session check failed:', err);
    }
    window.location.href = '/login.html';
    return false;
  },

  logout() {
    this.showConfirm('Log Out', 'Are you sure you want to log out?', async () => {
      try {
        const res = await fetch('/api/auth/logout', { method: 'POST' });
        if (res.ok) {
          localStorage.removeItem('user');
          window.location.href = '/login.html';
        }
      } catch (err) {
        this.showToast('Logout failed', 'error');
      }
    }, 'Log Out');
  },

  applyRoleCustomizations() {
    if (!this.user) return;

    // Set profile info
    document.getElementById('userName').textContent = this.user.username;
    document.getElementById('userAvatar').textContent = this.user.username.charAt(0).toUpperCase();
    
    let roleLabel = 'Super Admin';
    if (this.user.role === 'nvr_admin') roleLabel = 'NVR Admin';
    if (this.user.role === 'atm_admin') roleLabel = 'ATM Admin';
    document.getElementById('userRole').textContent = roleLabel;

    // Role visibility rules
    if (this.user.role === 'nvr_admin') {
      // Hide ATM and CRM options from settings, disable ATM/CRM additions
      document.getElementById('navSettings')?.style.setProperty('display', 'none');
      document.getElementById('addAtmBtn')?.style.setProperty('display', 'none');
      document.getElementById('addCrmBtn')?.style.setProperty('display', 'none');
    } else if (this.user.role === 'atm_admin') {
      // Hide settings, disable NVR/CAM additions
      document.getElementById('navSettings')?.style.setProperty('display', 'none');
      document.getElementById('navNvr')?.style.setProperty('margin-top', '0');
      document.querySelector('button[onclick="App.openAddDeviceModal(\'NVR\')"]')?.style.setProperty('display', 'none');
      document.querySelector('button[onclick="App.openAddDeviceModal(\'CAM\')"]')?.style.setProperty('display', 'none');
    }
  },

  // -------------------------------------------------------------------------
  // Real-time Updates (SignalR)
  // -------------------------------------------------------------------------
  initSocket() {
    this.socket = io({ path: "/socket.io" });

    const connDot = document.getElementById('connectionStatus');
    const connDotDot = connDot.querySelector('.status-dot');
    const connLabel = connDot.querySelector('.conn-label');

    this.socket.on('connect', () => {
      console.log('[socket] Connected to server.');
      connDotDot.className = 'status-dot online';
      connLabel.textContent = 'Live';
      connDot.title = 'Connected via Socket.IO';
    });

    this.socket.on('disconnect', () => {
      console.warn('[socket] Disconnected from server.');
      connDotDot.className = 'status-dot offline';
      connLabel.textContent = 'Disconnected';
      connDot.title = 'Server disconnected';
    });

    this.socket.on('connect_error', () => {
      console.warn('[socket] Connection error...');
      connDotDot.className = 'status-dot offline';
      connLabel.textContent = 'Reconnecting';
    });

    // Handle updates triggered by background monitoring
    this.socket.on('status_update', () => {
      console.log('[socket] Live status update received.');
      this.refreshData();
    });
  },

  // -------------------------------------------------------------------------
  // Navigation & Events
  // -------------------------------------------------------------------------
  setupEventListeners() {
    // Sidebar toggle (for mobile layout)
    document.getElementById('sidebarToggle').addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('active');
    });

    // View switching
    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const viewName = item.getAttribute('data-view');
        this.filterNvrWarnings = false;
        this.switchView(viewName);
        if (viewName === 'nvr') {
          this.renderNvrTable();
        }
        document.getElementById('sidebar').classList.remove('active');
      });
    });

    // Auto-update NVR settings endpoint example when API key input changes
    document.getElementById('atm_api_key')?.addEventListener('input', (e) => {
      this.updateAtmEndpointExample(e.target.value);
    });
  },

  switchView(viewName) {
    if (!viewName) return;
    this.currentView = viewName;

    // Update nav links
    document.querySelectorAll('.nav-item').forEach(item => {
      if (item.getAttribute('data-view') === viewName) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Update content area
    document.querySelectorAll('.view').forEach(view => {
      if (view.id === `view-${viewName}`) {
        view.classList.add('active');
      } else {
        view.classList.remove('active');
      }
    });

    // Update Header title
    const viewTitles = {
      dashboard: 'Dashboard',
      nvr: 'NVR Devices',
      cameras: 'Cameras',
      atm: 'ATM Devices',
      crm: 'CRM Devices',
      alerts: 'Alert Log',
      settings: 'Settings',
    };
    document.getElementById('viewTitle').textContent = viewTitles[viewName] || 'Monitor';

    // Lazy load views data
    if (viewName === 'settings') {
      this.loadSettings();
    } else if (viewName === 'alerts') {
      this.loadAlertLogs();
    } else {
      this.refreshData();
    }
  },

  // -------------------------------------------------------------------------
  // Data Loading & Rendering
  // -------------------------------------------------------------------------
  toggleSort(type, field) {
    if (field === 'name') {
      if (this.currentSort[type] === 'name_asc') {
        this.currentSort[type] = 'name_desc';
      } else {
        this.currentSort[type] = 'name_asc';
      }
    }
    this.renderTables();
  },

  applySorting(list, sortValue) {
    const sorted = [...list];
    switch (sortValue) {
      case 'name_asc':
        sorted.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case 'name_desc':
        sorted.sort((a, b) => b.name.localeCompare(a.name));
        break;
      // You can keep other sorting logic if you want to extend it later
      case 'status_on':
        sorted.sort((a, b) => {
          if (a.is_online === b.is_online) return a.name.localeCompare(b.name);
          return a.is_online ? -1 : 1;
        });
        break;
      case 'status_off':
        sorted.sort((a, b) => {
          if (a.is_online === b.is_online) return a.name.localeCompare(b.name);
          return !a.is_online ? -1 : 1;
        });
        break;
      case 'ip_asc':
        sorted.sort((a, b) => {
          const numA = (a.ip || '').split('.').map(n => +n).reduce((acc, val) => (acc << 8) + val, 0);
          const numB = (b.ip || '').split('.').map(n => +n).reduce((acc, val) => (acc << 8) + val, 0);
          return numA - numB;
        });
        break;
    }
    return sorted;
  },

  async refreshData() {
    try {
      // 1. Fetch Summary Stats
      const statsRes = await fetch('/api/dashboard');
      const statsResult = await statsRes.json();
      if (statsResult.success) {
        this.renderSummary(statsResult.data);
        this.renderCriticalAlerts(statsResult.data.criticalAlerts);
      }

      // Fetch Settings configuration
      try {
        const settingsRes = await fetch('/api/settings');
        const settingsResult = await settingsRes.json();
        if (settingsResult.success) {
          this.settings = settingsResult.data;
        }
      } catch (err) {
        console.error('[App] Failed to pre-fetch settings:', err);
      }

      // 2. Fetch All Devices
      const devicesRes = await fetch('/api/devices');
      const devicesResult = await devicesRes.json();
      if (devicesResult.success) {
        this.devices = devicesResult.data;
        this.renderGrids();
        this.renderTables();
        this.updateNewDashboard();
      }
    } catch (err) {
      console.error('[App] Error refreshing data:', err);
    }
  },

  renderSummary(data) {
    // Update summary count pills in header
    document.getElementById('pillTotalCount').textContent = data.total;
    document.getElementById('pillOnlineCount').textContent = data.online;
    document.getElementById('pillOfflineCount').textContent = data.offline;

    // Update home view cards if they exist (old dashboard)
    const td = document.getElementById('totalDevices');
    if (td) td.textContent = data.total;
    const od = document.getElementById('onlineDevices');
    if (od) od.textContent = data.online;
    const off = document.getElementById('offlineDevices');
    if (off) off.textContent = data.offline;
    const ni = document.getElementById('nvrIssues');
    if (ni) ni.textContent = data.criticalAlerts.filter(d => d.type === 'NVR' && d.is_online && d.nvr_recording === 0).length;
  },

  renderCriticalAlerts(alerts) {
    const badge = document.getElementById('criticalBadge');
    const pageBadge = document.getElementById('criticalPageBadge');
    const list = document.getElementById('criticalAlertsPageList');
    if (!list) return;

    list.innerHTML = '';

    if (!alerts || alerts.length === 0) {
      if (badge) badge.style.display = 'none';
      if (pageBadge) {
        pageBadge.textContent = '0 alerts';
        pageBadge.style.background = 'var(--accent-green)';
      }
      list.innerHTML = `
        <div class="empty-state" style="padding: 3rem; text-align: center;">
          <div style="font-size: 3rem; margin-bottom: 1rem;">🟢</div>
          <p style="color: var(--accent-green); font-weight: 600; font-size: 1.1rem;">No active critical alerts</p>
          <p style="color: var(--text-secondary); margin-top: 0.5rem;">All systems are fully operational and healthy.</p>
        </div>
      `;
      return;
    }

    if (badge) {
      badge.textContent = alerts.length;
      badge.style.display = 'inline-flex';
    }
    if (pageBadge) {
      pageBadge.textContent = `${alerts.length} alert${alerts.length > 1 ? 's' : ''}`;
      pageBadge.style.background = 'var(--accent-red)';
    }

    alerts.forEach(device => {
      const card = document.createElement('div');
      card.className = 'critical-alert-card';

      let title = '';
      let desc = '';
      let icon = '⚠️';

      if (!device.is_online) {
        icon = '🚨';
        title = `${device.type} Down`;
        desc = `Device ${device.name} (${device.ip}) is offline since ${device.down_since || 'just now'}.`;
      } else if (device.type === 'ATM') {
        if (device.atm_balance < 500000) {
          icon = '💰';
          title = 'ATM Low Cash';
          desc = `${device.name} balance is ${this.formatCurrency(device.atm_balance)} (under 5 Lakhs!).`;
        } else if (device.atm_status && device.atm_status !== 'Normal') {
          icon = '⚠️';
          title = 'ATM Malfunction';
          desc = `${device.name} reported error state [${device.atm_status}].`;
        }
      } else if (device.type === 'NVR' && !device.nvr_recording) {
        icon = '📹';
        title = 'NVR Stopped Recording';
        desc = `NVR ${device.name} (${device.ip}) is online but Hikvision checks indicate recording has stopped!`;
      }

      card.innerHTML = `
        <div class="ca-card-icon">${icon}</div>
        <div class="ca-card-content">
          <div class="ca-card-title">${title}</div>
          <div class="ca-card-desc">${desc}</div>
          <div class="ca-card-meta">Location: ${device.location || '--'} | Last Check: ${device.last_ping_time || '--'}</div>
        </div>
      `;
      list.appendChild(card);
    });
  },

  renderGrids() {
    const nvrGrid = document.getElementById('nvrGrid');
    const camGrid = document.getElementById('camGrid');
    const atmGrid = document.getElementById('atmGrid');
    const crmGrid = document.getElementById('crmGrid');

    if (!nvrGrid || !camGrid || !atmGrid || !crmGrid) return;

    nvrGrid.innerHTML = '';
    camGrid.innerHTML = '';
    atmGrid.innerHTML = '';
    crmGrid.innerHTML = '';

    let nvrs = this.devices.filter(d => d.type === 'NVR');
    let cams = this.devices.filter(d => d.type === 'CAM');
    let atms = this.devices.filter(d => d.type === 'ATM');
    let crms = this.devices.filter(d => d.type === 'CRM');

    // Section headers counts
    document.getElementById('nvrSectionCount').textContent = `${nvrs.length} devices`;
    document.getElementById('camSectionCount').textContent = `${cams.length} devices`;
    document.getElementById('atmSectionCount').textContent = `${atms.length} devices`;
    document.getElementById('crmSectionCount').textContent = `${crms.length} devices`;

    // Render NVR Cards
    if (nvrs.length === 0) {
      nvrGrid.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">No NVR devices registered</div>';
    } else {
      nvrs.forEach(d => {
        nvrGrid.innerHTML += this.createDeviceCardHtml(d);
      });
    }

    // Render Camera Cards
    if (cams.length === 0) {
      camGrid.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">No cameras registered</div>';
    } else {
      cams.forEach(d => {
        camGrid.innerHTML += this.createDeviceCardHtml(d);
      });
    }

    // Render ATM Cards
    if (atms.length === 0) {
      atmGrid.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">No ATM devices registered</div>';
    } else {
      atms.forEach(d => {
        atmGrid.innerHTML += this.createDeviceCardHtml(d);
      });
    }

    // Render CRM Cards
    if (crms.length === 0) {
      crmGrid.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">No CRM devices registered</div>';
    } else {
      crms.forEach(d => {
        crmGrid.innerHTML += this.createDeviceCardHtml(d);
      });
    }
  },

  createDeviceCardHtml(device) {
    const statusClass = device.is_online ? 'online' : 'offline';
    const statusText = device.is_online ? 'Online' : 'Offline';

    let cardMetaHtml = '';
    let extraDetailsHtml = '';

    if (device.type === 'NVR') {
      const recordingText = device.is_online ? (device.nvr_recording ? 'Recording' : 'Stop / Issue') : 'N/A';
      const recordingClass = device.nvr_recording ? 'recording-ok' : 'recording-issue';
      
      const hddText = device.nvr_hdd_status || 'Unknown';
      const hddClass = hddText === 'Healthy' ? 'recording-ok' : (hddText === 'HDD Error' ? 'recording-issue' : 'recording-unknown');
      
      const lastRecText = this.getRelativeTime(device.nvr_last_recording);
      
      const nvrCameras = this.devices.filter(c => c.type === 'CAM' && c.parent_nvr_id === device.id);
      let camStatusText = 'N/A';
      let camStatusClass = 'recording-unknown';
      if (device.is_online && nvrCameras.length > 0) {
        const onlineCams = nvrCameras.filter(c => c.is_online).length;
        camStatusText = `${onlineCams}/${nvrCameras.length} OK`;
        camStatusClass = onlineCams === nvrCameras.length ? 'recording-ok' : 'recording-issue';
      }

      extraDetailsHtml = `
        <div class="nvr-card-details" style="display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; margin-top: 0.5rem; border-top: 1px solid var(--border-color); padding-top: 0.5rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">HDD Status:</span>
            <span class="device-card-badge ${hddClass}" style="padding: 1px 6px; font-size: 0.75rem;">${hddText}</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">Last Recording:</span>
            <span style="font-weight: 500;">${lastRecText}</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">Camera Status:</span>
            <span class="device-card-badge ${camStatusClass}" style="padding: 1px 6px; font-size: 0.75rem;">${camStatusText}</span>
          </div>
        </div>
      `;

      cardMetaHtml = `
        <span class="device-latency">Ping: ${device.last_latency !== null ? Math.round(device.last_latency) + ' ms' : '--'}</span>
        <span class="device-card-badge ${recordingClass}">${recordingText}</span>
      `;
    } else if (device.type === 'CAM') {
      const parentNvr = this.devices.find(d => d.id === device.parent_nvr_id);
      cardMetaHtml = `
        <span class="device-latency">Ping: ${device.last_latency !== null ? Math.round(device.last_latency) + ' ms' : '--'}</span>
        <span style="font-size:0.75rem; color:var(--text-secondary)">${parentNvr ? 'NVR: ' + parentNvr.name : 'Standalone'}</span>
      `;
    } else if (device.type === 'ATM') {
      const isLowBalance = device.atm_balance < 500000;
      const isError = device.atm_status && device.atm_status !== 'Normal';
      extraDetailsHtml = `
        <div class="atm-details">
          <div class="atm-balance-row">
            <span>Cash Balance:</span>
            <span class="atm-balance-val ${isLowBalance ? 'low' : ''}">${this.formatCurrency(device.atm_balance)}</span>
          </div>
          <div class="atm-status-row">
            <span>ATM Status:</span>
            <span class="atm-status-val ${isError ? 'error' : ''}">${device.atm_status || 'Normal'}</span>
          </div>
        </div>
      `;
      cardMetaHtml = `
        <span class="device-latency">Ping: ${device.last_latency !== null ? Math.round(device.last_latency) + ' ms' : '--'}</span>
        <span style="font-size:0.75rem; color:var(--text-muted)">Update: ${device.atm_last_updated ? device.atm_last_updated.split(' ')[1] : '--'}</span>
      `;
    } else if (device.type === 'CRM') {
      cardMetaHtml = `
        <span class="device-latency">Ping: ${device.last_latency !== null ? Math.round(device.last_latency) + ' ms' : '--'}</span>
        <span style="font-size:0.75rem; color:var(--text-muted)">Loss: ${device.last_packet_loss}%</span>
      `;
    }

    return `
      <div class="device-card">
        <div class="device-card-header">
          <span class="device-card-name">${device.name}</span>
          <span class="status-dot ${statusClass}" title="${statusText}"></span>
        </div>
        <span class="device-card-ip">${device.ip}</span>
        ${extraDetailsHtml}
        <div class="device-card-location">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
          <span>${device.location || 'Unknown location'}</span>
        </div>
        <div class="device-card-meta">
          ${cardMetaHtml}
        </div>
      </div>
    `;
  },


  renderTables() {
    this.renderNvrTable();
    this.renderCamTable();
    this.renderAtmTable();
    this.renderGenericDeviceTable('CRM', 'crmTableBody', 'crmEmptyState', 'crmTable');
    this.renderGenericDeviceTable('Router', 'routerTableBody', 'routerEmptyState', 'routerTable');
    this.renderGenericDeviceTable('Server', 'serverTableBody', 'serverEmptyState', 'serverTable');
    this.renderAllNodesTable();
  },

  renderNvrTable() {
    const body = document.getElementById('nvrTableBody');
    const emptyState = document.getElementById('nvrEmptyState');
    const sortIcon = document.getElementById('nvrSortIcon');
    body.innerHTML = '';

    if (sortIcon) {
      sortIcon.textContent = this.currentSort['NVR'] === 'name_asc' ? '▲' : '▼';
    }

    let list = this.devices.filter(d => d.type === 'NVR');
    if (this.filterNvrWarnings) {
      list = list.filter(d => d.is_online && !d.nvr_recording);
      document.getElementById('nvrPageCount').innerHTML = `${list.length} devices <span class="badge" style="background:var(--accent-amber); color:black; margin-left:8px; font-weight: 600;">Warnings Filter Active</span>`;
    } else {
      document.getElementById('nvrPageCount').textContent = `${list.length} devices`;
    }
    list = this.applySorting(list, this.currentSort['NVR']);

    if (list.length === 0) {
      emptyState.style.display = 'block';
      document.getElementById('nvrTable').style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';
    document.getElementById('nvrTable').style.display = 'table';

    list.forEach(d => {
      const pingText = d.is_online ? `${Math.round(d.last_latency)} ms (${d.last_packet_loss}% loss)` : 'Offline';
      const statusClass = d.is_online ? 'online' : 'offline';

      let hddHtml = 'N/A';
      let lastRecHtml = this.getRelativeTime(d.nvr_last_recording);
      let camHtml = 'N/A';

      const nvrCameras = this.devices.filter(c => c.type === 'CAM' && c.parent_nvr_id === d.id);

      const hddText = d.nvr_hdd_status || 'Unknown';
      const hddBadgeClass = hddText === 'Healthy' ? 'recording-ok' : (hddText === 'HDD Error' ? 'recording-issue' : 'recording-unknown');
      
      let spaceInfo = '';
      if (d.nvr_hdd_capacity && d.nvr_hdd_used) {
        spaceInfo = `<div style="font-size: 0.68rem; color: var(--text-secondary); margin-top: 4px; font-weight: 500; white-space: nowrap;">Used: ${d.nvr_hdd_used} / ${d.nvr_hdd_capacity}</div>`;
      }
      hddHtml = `<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;">
        <span class="device-card-badge ${hddBadgeClass}">${hddText}</span>
        ${spaceInfo}
      </div>`;

      if (d.is_online) {
        if (nvrCameras.length > 0) {
          const onlineCams = nvrCameras.filter(c => c.is_online).length;
          const allCamsOk = onlineCams === nvrCameras.length;
          const camBadgeClass = allCamsOk ? 'recording-ok' : 'recording-issue';
          camHtml = `<span class="device-card-badge ${camBadgeClass}">${onlineCams}/${nvrCameras.length} OK</span>`;
        } else {
          camHtml = '0/0 OK';
        }
      }

      const showActions = this.user.role === 'super_admin' || this.user.role === 'nvr_admin';

      body.innerHTML += `
        <tr onclick="App.toggleNvrCameras(${d.id})" style="cursor: pointer;" class="nvr-main-row" title="Click to show/hide connected cameras">
          <td><span class="status-dot ${statusClass}"></span></td>
          <td><strong style="color: var(--accent-blue);">${d.name}</strong></td>
          <td><span class="device-card-ip">${d.ip}</span></td>
          <td>${d.location || '--'}</td>
          <td>${pingText}</td>
          <td>${hddHtml}</td>
          <td>${lastRecHtml}</td>
          <td>${camHtml}</td>
          <td id="nvr-time-diff-${d.id}"><span style="color:var(--text-muted)">--</span></td>
          <td>
            ${showActions ? `
              <button class="btn btn-ghost btn-icon-only" onclick="event.stopPropagation(); App.syncNvrTime(${d.id})" title="Sync NVR Clock with NTP Server">
                ⏰
              </button>
              <button class="btn btn-ghost btn-icon-only" onclick="event.stopPropagation(); App.openEditDeviceModal(${d.id})" title="Edit">
                ✏️
              </button>
              <button class="btn btn-danger btn-icon-only" onclick="event.stopPropagation(); App.confirmDelete(${d.id})" title="Delete">
                🗑️
              </button>
            ` : '--'}
          </td>
        </tr>
        <tr id="nvr-cams-${d.id}" class="nvr-cams-subrow" style="display: none; background: rgba(255, 255, 255, 0.015);">
          <td colspan="10" style="padding: 0;">
            <div style="padding: 0.75rem 1.5rem; display: flex; flex-direction: column; gap: 0.5rem; border-left: 4px solid var(--accent-blue); text-align: left;">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem;">
                <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-secondary);">Connected Cameras (${nvrCameras.length})</div>
                ${nvrCameras.length > 0 && showActions ? `
                  <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.75rem;">
                    <span style="color: var(--text-secondary);">Set all main stream:</span>
                    <select onchange="App.batchChangeCameraResolution(${d.id}, this.value); this.value='';" style="background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 4px; padding: 2px 4px; font-size: 0.75rem; cursor: pointer;">
                      <option value="">Select resolution...</option>
                      <option value="1920x1080">1080p (1920x1080)</option>
                      <option value="1280x720">720p (1280x720)</option>
                      <option value="704x576">D1 (704x576)</option>
                      <option value="640x480">VGA (640x480)</option>
                      <option value="352x288">CIF (352x288)</option>
                    </select>
                  </div>
                ` : ''}
              </div>
              ${nvrCameras.length === 0 ? `
                <div style="font-size: 0.8rem; color: var(--text-muted);">No cameras registered under this NVR.</div>
              ` : `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 1rem; width: 100%;">
                  ${nvrCameras.map(c => {
                    const camStatusClass = c.is_online ? 'online' : 'offline';
                    const camPingText = c.is_online ? `${Math.round(c.last_latency)} ms` : 'Offline';
                    return `
                      <div style="background: rgba(30, 41, 59, 0.45); padding: 1.25rem; border-radius: 12px; display: flex; flex-direction: column; gap: 0.75rem; border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4); height: 100%;">
                        <!-- Card Header -->
                        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 0.75rem; margin-bottom: 0.25rem;">
                          <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
                            <span class="status-dot ${camStatusClass}" style="width: 10px; height: 10px;"></span>
                            <span style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary); margin-right: 6px;">${c.name}</span>
                            ${c.is_online ? `<button class="btn btn-ghost btn-icon-only" onclick="App.openCameraLiveModal(${c.id}, '${c.name}')" title="Live Preview" style="padding: 2px; font-size: 0.82rem; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; height: 20px; width: 20px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.05); outline: none;">👁️</button>` : ''}
                          </div>
                          <span style="font-size: 0.72rem; color: var(--text-secondary); font-weight: 500;">${c.ip} (${camPingText})</span>
                        </div>
                        
                        <!-- 2-Column Configuration Grid -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; row-gap: 14px; column-gap: 24px; flex: 1; align-content: start;">
                          <!-- Field 1: Resolution (Main) -->
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                            <span style="font-size: 0.75rem; font-weight: 500; color: var(--text-secondary); white-space: nowrap;">Resolution (Main):</span>
                            <select id="cam-${c.id}-main-res" disabled onchange="App.changeCameraResolution(${c.id}, 'main', this.value)" style="background: rgba(15, 23, 42, 0.6); color: var(--text-primary); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 8px; font-size: 0.72rem; outline: none; cursor: pointer; flex: 1; min-width: 135px; max-width: 180px; text-align: left;">
                              <option value="">Loading...</option>
                            </select>
                          </div>
                          
                          <!-- Field 2: Resolution (Sub) -->
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                            <span style="font-size: 0.75rem; font-weight: 500; color: var(--text-secondary); white-space: nowrap;">Resolution (Sub):</span>
                            <select id="cam-${c.id}-sub-res" disabled onchange="App.changeCameraResolution(${c.id}, 'sub', this.value)" style="background: rgba(15, 23, 42, 0.6); color: var(--text-primary); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 8px; font-size: 0.72rem; outline: none; cursor: pointer; flex: 1; min-width: 135px; max-width: 180px; text-align: left;">
                              <option value="">Loading...</option>
                            </select>
                          </div>
                          
                          <!-- Field 3: FPS -->
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                            <span style="font-size: 0.75rem; font-weight: 500; color: var(--text-secondary); white-space: nowrap;">Framerate (FPS):</span>
                            <select id="cam-${c.id}-main-fps" disabled onchange="App.changeCameraFramerate(${c.id}, this.value)" style="background: rgba(15, 23, 42, 0.6); color: var(--text-primary); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 8px; font-size: 0.72rem; outline: none; cursor: pointer; flex: 1; min-width: 135px; max-width: 180px; text-align: left;">
                              <option value="">Loading...</option>
                            </select>
                          </div>
                          
                          <!-- Field 4: Protocol -->
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                            <span style="font-size: 0.75rem; font-weight: 500; color: var(--text-secondary); white-space: nowrap;">Protocol:</span>
                            <select id="cam-${c.id}-main-proto" disabled onchange="App.changeCameraProtocol(${c.id}, this.value)" style="background: rgba(15, 23, 42, 0.6); color: var(--text-primary); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 8px; font-size: 0.72rem; outline: none; cursor: pointer; flex: 1; min-width: 135px; max-width: 180px; text-align: left;">
                              <option value="">Loading...</option>
                            </select>
                          </div>
                          
                          <!-- Field 5: Bitrate -->
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                            <span style="font-size: 0.75rem; font-weight: 500; color: var(--text-secondary); white-space: nowrap;">Bitrate Limit:</span>
                            <select id="cam-${c.id}-main-bitrate" disabled onchange="App.changeCameraBitrate(${c.id}, this.value)" style="background: rgba(15, 23, 42, 0.6); color: var(--text-primary); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 8px; font-size: 0.72rem; outline: none; cursor: pointer; flex: 1; min-width: 135px; max-width: 180px; text-align: left;">
                              <option value="">Loading...</option>
                            </select>
                          </div>
                          
                          <!-- Field 6: Rec Range History -->
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                            <span style="font-size: 0.75rem; font-weight: 500; color: var(--text-secondary); white-space: nowrap;">Rec History:</span>
                            <div id="cam-range-${c.id}" style="font-size: 0.72rem; color: var(--text-primary); font-weight: 600; text-align: right; flex: 1; white-space: nowrap;">
                              <span style="font-style: italic; color: var(--text-muted); font-weight: normal;">Loading...</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    `;
                  }).join('')}
                </div>
              `}
            </div>
          </td>
        </tr>
      `;
    });

    this.loadNvrTimeDifferences();
  },

  renderCamTable() {
    const body = document.getElementById('camTableBody');
    const emptyState = document.getElementById('camEmptyState');
    const sortIcon = document.getElementById('camSortIcon');
    body.innerHTML = '';

    if (sortIcon) {
      sortIcon.textContent = this.currentSort['CAM'] === 'name_asc' ? '▲' : '▼';
    }

    let list = this.devices.filter(d => d.type === 'CAM');
    document.getElementById('camPageCount').textContent = `${list.length} devices`;
    list = this.applySorting(list, this.currentSort['CAM']);

    if (list.length === 0) {
      emptyState.style.display = 'block';
      document.getElementById('camTable').style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';
    document.getElementById('camTable').style.display = 'table';

    list.forEach(d => {
      const parentNvr = this.devices.find(n => n.id === d.parent_nvr_id);
      const pingText = d.is_online ? `${Math.round(d.last_latency)} ms` : 'Offline';
      const statusClass = d.is_online ? 'online' : 'offline';

      const showActions = this.user.role === 'super_admin' || this.user.role === 'nvr_admin';

      body.innerHTML += `
        <tr>
          <td><span class="status-dot ${statusClass}"></span></td>
          <td><strong>${d.name}</strong></td>
          <td><span class="device-card-ip">${d.ip}</span></td>
          <td>${d.location || '--'}</td>
          <td>${parentNvr ? parentNvr.name : 'Standalone'}</td>
          <td>${pingText}</td>
          <td>
            ${showActions ? `
              <button class="btn btn-ghost btn-icon-only" onclick="App.openEditDeviceModal(${d.id})">✏️</button>
              <button class="btn btn-danger btn-icon-only" onclick="App.confirmDelete(${d.id})">🗑️</button>
            ` : '--'}
          </td>
        </tr>
      `;
    });
  },

  renderAtmTable() {
    const body = document.getElementById('atmTableBody');
    const emptyState = document.getElementById('atmEmptyState');
    const sortIcon = document.getElementById('atmSortIcon');
    body.innerHTML = '';

    if (sortIcon) {
      sortIcon.textContent = this.currentSort['ATM'] === 'name_asc' ? '▲' : '▼';
    }

    let list = this.devices.filter(d => d.type === 'ATM');
    document.getElementById('atmPageCount').textContent = `${list.length} devices`;
    list = this.applySorting(list, this.currentSort['ATM']);

    if (list.length === 0) {
      emptyState.style.display = 'block';
      document.getElementById('atmTable').style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';
    document.getElementById('atmTable').style.display = 'table';

    list.forEach(d => {
      const pingText = d.is_online ? `${Math.round(d.last_latency)} ms` : 'Offline';
      const statusClass = d.is_online ? 'online' : 'offline';
      
      const isLowBalance = d.atm_balance < 500000;
      const isError = d.atm_status && d.atm_status !== 'Normal';

      const showActions = this.user.role === 'super_admin' || this.user.role === 'atm_admin';

      body.innerHTML += `
        <tr>
          <td><span class="status-dot ${statusClass}"></span></td>
          <td><strong>${d.name}</strong></td>
          <td><span class="device-card-ip">${d.ip}</span></td>
          <td>${d.location || '--'}</td>
          <td>${pingText}</td>
          <td class="atm-balance-val ${isLowBalance ? 'low' : ''}" style="font-weight: 700;">${this.formatCurrency(d.atm_balance)}</td>
          <td class="atm-status-val ${isError ? 'error' : ''}" style="font-weight: 600;">${d.atm_status || 'Normal'}</td>
          <td>${d.atm_last_updated || '--'}</td>
          <td>
            ${showActions ? `
              <button class="btn btn-ghost btn-icon-only" onclick="App.openEditDeviceModal(${d.id})">✏️</button>
              <button class="btn btn-danger btn-icon-only" onclick="App.confirmDelete(${d.id})">🗑️</button>
            ` : '--'}
          </td>
        </tr>
      `;
    });
  },

  renderGenericDeviceTable(type, bodyId, emptyStateId, tableId) {
    const body = document.getElementById(bodyId);
    const emptyState = document.getElementById(emptyStateId);
    const table = document.getElementById(tableId);
    if (!body || !emptyState || !table) return;

    body.innerHTML = '';
    const list = this.devices.filter(d => d.type === type);

    if (list.length === 0) {
      emptyState.style.display = 'block';
      table.style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';
    table.style.display = 'table';

    list.forEach(d => {
      const pingText = d.is_online ? `${Math.round(d.last_latency)} ms (${d.last_packet_loss}% loss)` : 'Offline';
      const statusClass = d.is_online ? 'online' : 'offline';
      const showActions = this.user.role === 'super_admin' || this.user.role === 'atm_admin';

      body.innerHTML += `
        <tr>
          <td><span class="status-dot ${statusClass}"></span></td>
          <td><strong>${d.name}</strong></td>
          <td><span class="device-card-ip">${d.ip}</span></td>
          <td>${d.location || '--'}</td>
          <td>${pingText}</td>
          <td>
            ${showActions ? `
              <button class="btn btn-ghost btn-icon-only" onclick="event.stopPropagation(); App.openEditDeviceModal(${d.id})">✏️</button>
              <button class="btn btn-danger btn-icon-only" onclick="event.stopPropagation(); App.confirmDelete(${d.id})">🗑️</button>
            ` : '--'}
          </td>
        </tr>
      `;
    });
  },

  renderAllNodesTable() {
    const body = document.getElementById('allNodesTableBody');
    if (!body) return;
    body.innerHTML = '';
    const list = this.devices || [];

    list.forEach(d => {
      const pingText = d.is_online ? `${Math.round(d.last_latency)} ms (${d.last_packet_loss}% loss)` : 'Offline';
      const statusClass = d.is_online ? 'online' : 'offline';

      body.innerHTML += `
        <tr>
          <td><span class="status-dot ${statusClass}"></span></td>
          <td><strong>${d.type}</strong></td>
          <td><strong>${d.name}</strong></td>
          <td><span class="device-card-ip">${d.ip}</span></td>
          <td>${d.location || '--'}</td>
          <td>${pingText}</td>
        </tr>
      `;
    });
  },

  // -------------------------------------------------------------------------
  // Device CRUD Actions
  // -------------------------------------------------------------------------
  openAddDeviceModal(type) {
    document.getElementById('deviceModalTitle').textContent = `Add ${type}`;
    document.getElementById('deviceId').value = '';
    document.getElementById('deviceName').value = '';
    document.getElementById('deviceIp').value = '';
    document.getElementById('deviceType').value = type;
    document.getElementById('deviceLocation').value = '';
    document.getElementById('deviceNotes').value = '';
    
    document.getElementById('hikUsername').value = 'admin';
    document.getElementById('hikPassword').value = '';

    this.populateParentNvrDropdown();
    this.toggleDeviceTypeFields();

    document.getElementById('deviceModalOverlay').classList.add('active');
  },

  openEditDeviceModal(id) {
    const device = this.devices.find(d => d.id === id);
    if (!device) return;

    document.getElementById('deviceModalTitle').textContent = 'Edit Device';
    document.getElementById('deviceId').value = device.id;
    document.getElementById('deviceName').value = device.name;
    document.getElementById('deviceIp').value = device.ip;
    document.getElementById('deviceType').value = device.type;
    document.getElementById('deviceLocation').value = device.location || '';
    document.getElementById('deviceNotes').value = device.notes || '';
    
    document.getElementById('hikUsername').value = device.hik_username || 'admin';
    document.getElementById('hikPassword').value = device.hik_password || '';

    this.populateParentNvrDropdown(device.parent_nvr_id);
    this.toggleDeviceTypeFields();

    document.getElementById('deviceModalOverlay').classList.add('active');
  },

  closeDeviceModal() {
    document.getElementById('deviceModalOverlay').classList.remove('active');
  },

  toggleDeviceTypeFields() {
    const type = document.getElementById('deviceType').value;
    const nvrFields = document.getElementById('nvrFields');
    const camFields = document.getElementById('camFields');

    if (type === 'NVR') {
      nvrFields.style.display = 'block';
      camFields.style.display = 'none';
    } else if (type === 'CAM') {
      nvrFields.style.display = 'none';
      camFields.style.display = 'block';
    } else {
      // ATM or CRM
      nvrFields.style.display = 'none';
      camFields.style.display = 'none';
    }
  },

  populateParentNvrDropdown(selectedId = null) {
    const dropdown = document.getElementById('parentNvrId');
    dropdown.innerHTML = '<option value="">None (standalone)</option>';

    const nvrs = this.devices.filter(d => d.type === 'NVR');
    nvrs.forEach(n => {
      const selectedAttr = selectedId === n.id ? 'selected' : '';
      dropdown.innerHTML += `<option value="${n.id}" ${selectedAttr}>${n.name} (${n.ip})</option>`;
    });
  },

  async saveDevice() {
    const id = document.getElementById('deviceId').value;
    const name = document.getElementById('deviceName').value.trim();
    const ip = document.getElementById('deviceIp').value.trim();
    const type = document.getElementById('deviceType').value;
    const location = document.getElementById('deviceLocation').value.trim();
    const notes = document.getElementById('deviceNotes').value.trim();
    
    const hik_username = document.getElementById('hikUsername').value.trim();
    const hik_password = document.getElementById('hikPassword').value;
    const parent_nvr_id = document.getElementById('parentNvrId').value || null;

    if (!name || !ip) {
      this.showToast('Name and IP Address are required', 'warning');
      return;
    }

    const payload = {
      name,
      ip,
      type,
      location,
      notes,
      hik_username: type === 'NVR' ? hik_username : null,
      hik_password: type === 'NVR' ? hik_password : null,
      parent_nvr_id: type === 'CAM' ? (parent_nvr_id ? Number(parent_nvr_id) : null) : null,
    };

    try {
      let response;
      if (id) {
        // Edit Mode
        response = await fetch(`/api/devices/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        // Add Mode
        response = await fetch('/api/devices', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }

      const result = await response.json();

      if (response.ok && result.success) {
        this.showToast(id ? 'Device updated' : 'Device added', 'success');
        this.closeDeviceModal();
        await this.refreshData();
      } else {
        this.showToast(result.error || 'Failed to save device', 'error');
      }
    } catch (err) {
      console.error('[App] Error saving device:', err);
      this.showToast('Connection failed', 'error');
    }
  },

  confirmDelete(id) {
    const device = this.devices.find(d => d.id === id);
    if (!device) return;

    this.deleteTargetId = id;
    this.showConfirm(
      'Delete Device',
      `Are you sure you want to delete device <strong>${device.name}</strong> (${device.ip})?`,
      async () => {
        try {
          const res = await fetch(`/api/devices/${this.deleteTargetId}`, { method: 'DELETE' });
          const result = await res.json();
          if (res.ok && result.success) {
            this.showToast('Device deleted successfully', 'success');
            await this.refreshData();
          } else {
            this.showToast(result.error || 'Failed to delete device', 'error');
          }
        } catch (err) {
          this.showToast('Delete connection error', 'error');
        } finally {
          this.deleteTargetId = null;
        }
      },
      'Delete'
    );
  },

  async checkNvrRecording(id) {
    this.showToast('Checking NVR recording status...', 'info');
    try {
      const res = await fetch(`/api/devices/${id}/check-nvr`, { method: 'POST' });
      const result = await res.json();
      if (res.ok && result.success) {
        const checkResult = result.data;
        if (checkResult.success) {
          const isRec = checkResult.isRecording;
          const hdd = checkResult.hddStatus || 'Unknown';
          this.showToast(
            isRec ? `NVR is actively recording! (HDD: ${hdd})` : `NVR is NOT recording! (HDD: ${hdd})`,
            isRec ? 'success' : 'warning'
          );
        } else {
          this.showToast(`Recording check failed: ${checkResult.error || 'NVR is unreachable'}`, 'error');
        }
        await this.refreshData();
      } else {
        this.showToast(result.error || 'Recording check failed', 'error');
      }
    } catch (err) {
      this.showToast('Connection failed', 'error');
    }
  },

  async checkAllNvrs() {
    this.showToast('Refreshing all NVR devices...', 'info');
    const nvrs = this.devices.filter(d => d.type === 'NVR');
    if (nvrs.length === 0) {
      this.showToast('No NVR devices to refresh', 'warning');
      return;
    }

    let successCount = 0;
    let failCount = 0;

    // Run them in parallel batches of 5 to not overload connection limit or server
    const batchSize = 5;
    for (let i = 0; i < nvrs.length; i += batchSize) {
      const batch = nvrs.slice(i, i + batchSize);
      await Promise.all(batch.map(async (nvr) => {
        try {
          const res = await fetch(`/api/devices/${nvr.id}/check-nvr`, { method: 'POST' });
          const result = await res.json();
          if (res.ok && result.success && result.data.success) {
            successCount++;
          } else {
            failCount++;
          }
        } catch (err) {
          failCount++;
        }
      }));
    }

    await this.refreshData();

    if (failCount === 0) {
      this.showToast(`Successfully refreshed all ${successCount} NVRs!`, 'success');
    } else {
      this.showToast(`NVR refresh complete: ${successCount} succeeded, ${failCount} failed.`, 'warning');
    }
  },

  // -------------------------------------------------------------------------
  // Settings view
  // -------------------------------------------------------------------------
  async loadSettings() {
    try {
      const res = await fetch('/api/settings');
      const result = await res.json();
      if (res.ok && result.success) {
        this.settings = result.data;
        
        // Fill fields
        for (const [key, value] of Object.entries(this.settings)) {
          const el = document.getElementById(key);
          if (el) {
            if (el.type === 'checkbox') {
              el.checked = value === 'true';
            } else {
              el.value = value;
            }
          }
        }
        this.updateAtmEndpointExample(this.settings.atm_api_key);
      }
    } catch (err) {
      console.error('[App] loadSettings error:', err);
    }
  },

  updateAtmEndpointExample(apiKey) {
    const key = apiKey || 'adc_atm_secret_key_2026';
    const serverIp = window.location.host;
    const field = document.getElementById('atm_endpoint_example');
    if (field) {
      field.value = `http://${serverIp}/api/atm/status?apiKey=${key}`;
    }
  },

  async saveSettings() {
    const updates = {};
    const keys = [
      'smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'smtp_from', 'smtp_secure', 'email_recipients',
      'sms_api_url', 'sms_api_method', 'sms_api_headers', 'sms_api_body_template', 'sms_recipients',
      'ping_interval_minutes', 'nvr_check_interval_minutes', 'email_alert_after_minutes', 'sms_alert_after_minutes',
      'atm_api_key', 'ntp_server_ip', 'ntp_server_port'
    ];

    keys.forEach(key => {
      const el = document.getElementById(key);
      if (el) {
        if (el.type === 'checkbox') {
          updates[key] = el.checked ? 'true' : 'false';
        } else {
          updates[key] = el.value.trim();
        }
      }
    });

    try {
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      const result = await res.json();
      if (res.ok && result.success) {
        this.showToast('Settings saved successfully', 'success');
        this.settings = result.data;
      } else {
        this.showToast(result.error || 'Failed to save settings', 'error');
      }
    } catch (err) {
      this.showToast('Connection failed', 'error');
    }
  },

  // Test notification triggers
  testEmail() {
    const email = prompt('Enter recipient email for SMTP test:');
    if (!email) return;
    this.showToast('Sending SMTP test email...', 'info');
    fetch('/api/settings/test-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: email })
    })
    .then(res => res.json())
    .then(res => {
      if (res.success) this.showToast('Test email sent successfully!', 'success');
      else this.showToast(res.error || 'SMTP test failed', 'error');
    })
    .catch(() => this.showToast('Connection error', 'error'));
  },

  testSms() {
    const phone = prompt('Enter recipient phone number for SMS test:');
    if (!phone) return;
    this.showToast('Sending test SMS...', 'info');
    fetch('/api/settings/test-sms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: phone, message: 'ADC Monitor Test SMS' })
    })
    .then(res => res.json())
    .then(res => {
      if (res.success) this.showToast('Test SMS sent successfully!', 'success');
      else this.showToast(res.error || 'SMS test failed', 'error');
    })
    .catch(() => this.showToast('Connection error', 'error'));
  },

  // -------------------------------------------------------------------------
  // Alert logs view
  // -------------------------------------------------------------------------
  async loadAlertLogs() {
    try {
      const res = await fetch('/api/alerts?limit=50');
      const result = await res.json();
      const body = document.getElementById('alertsTableBody');
      const emptyState = document.getElementById('alertsEmptyState');
      
      body.innerHTML = '';

      if (!res.ok || !result.success || result.data.length === 0) {
        emptyState.style.display = 'block';
        document.getElementById('alertsTable').style.display = 'none';
        return;
      }

      emptyState.style.display = 'none';
      document.getElementById('alertsTable').style.display = 'table';

      result.data.forEach(log => {
        const device = this.devices.find(d => d.id === log.device_id);
        const deviceName = device ? `${device.name} (${device.ip})` : `Device ID: ${log.device_id}`;
        const typeBadge = log.alert_type.toUpperCase();
        const successText = log.success ? 'Success' : 'Failed';
        const successClass = log.success ? 'recording-ok' : 'recording-issue';

        body.innerHTML += `
          <tr>
            <td>${log.sent_at}</td>
            <td><strong>${deviceName}</strong></td>
            <td><span class="pill" style="border:none; padding: 0.15rem 0.5rem; font-size:0.75rem;">${typeBadge}</span></td>
            <td>${log.message}</td>
            <td><span class="device-card-badge ${successClass}">${successText}</span></td>
          </tr>
        `;
      });
    } catch (err) {
      console.error('[App] loadAlertLogs error:', err);
    }
  },

  async clearAllAlerts() {
    if (!confirm('Are you sure you want to clear all alert logs?')) return;
    try {
      const res = await fetch('/api/alerts', { method: 'DELETE' });
      if (res.ok) {
        this.showToast('Alert logs cleared', 'success');
        await this.loadAlertLogs();
      }
    } catch (err) {
      this.showToast('Connection failed', 'error');
    }
  },

  // -------------------------------------------------------------------------
  // Dialogs & Toasts UI Helpers
  // -------------------------------------------------------------------------
  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    if (type === 'warning') icon = '⚠️';

    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    // Fade out and remove
    setTimeout(() => {
      toast.style.animation = 'toastIn 0.3s cubic-bezier(0.68, -0.55, 0.27, 1.55) reverse forwards';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  showConfirm(title, message, onOk, okText = 'Ok') {
    const overlay = document.getElementById('confirmOverlay');
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').innerHTML = message;
    
    const cancelBtn = document.getElementById('confirmCancel');
    const okBtn = document.getElementById('confirmOk');
    okBtn.textContent = okText;

    const closeConfirm = () => {
      overlay.classList.remove('active');
      okBtn.removeEventListener('click', okHandler);
      cancelBtn.removeEventListener('click', cancelHandler);
    };

    const okHandler = () => {
      onOk();
      closeConfirm();
    };

    const cancelHandler = () => {
      closeConfirm();
    };

    okBtn.addEventListener('click', okHandler);
    cancelBtn.addEventListener('click', cancelHandler);
    overlay.classList.add('active');
  },

  parseCustomDate(dateStr) {
    if (!dateStr) return null;
    let date = new Date(dateStr);
    if (!isNaN(date.getTime())) return date;

    // Try parsing DD/MM/YYYY, hh:mm:ss am/pm
    const parts = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})\s*(am|pm)?/i);
    if (parts) {
      const day = parseInt(parts[1], 10);
      const month = parseInt(parts[2], 10) - 1; // 0-indexed
      const year = parseInt(parts[3], 10);
      let hour = parseInt(parts[4], 10);
      const min = parseInt(parts[5], 10);
      const sec = parseInt(parts[6], 10);
      const ampm = parts[7] ? parts[7].toLowerCase() : null;

      if (ampm === 'pm' && hour < 12) hour += 12;
      if (ampm === 'am' && hour === 12) hour = 0;

      const parsed = new Date(year, month, day, hour, min, sec);
      if (!isNaN(parsed.getTime())) return parsed;
    }
    return null;
  },

  getRelativeTime(dateStr) {
    if (!dateStr) return 'N/A';
    return dateStr;
  },

  toggleNvrCameras(nvrId) {
    const subrow = document.getElementById(`nvr-cams-${nvrId}`);
    if (subrow) {
      const isHidden = subrow.style.display === 'none';
      subrow.style.display = isHidden ? 'table-row' : 'none';
      if (isHidden) {
        this.loadNvrCamerasResolutions(nvrId);
        this.loadNvrCamerasRecordingRanges(nvrId);
      }
    }
  },

  async loadNvrCamerasResolutions(nvrId) {
    const nvrCameras = this.devices.filter(c => c.type === 'CAM' && c.parent_nvr_id === nvrId);
    for (const cam of nvrCameras) {
      const mainSelect = document.getElementById(`cam-${cam.id}-main-res`);
      const subSelect = document.getElementById(`cam-${cam.id}-sub-res`);
      const fpsSelect = document.getElementById(`cam-${cam.id}-main-fps`);
      const bitrateSelect = document.getElementById(`cam-${cam.id}-main-bitrate`);
      const protoSelect = document.getElementById(`cam-${cam.id}-main-proto`);
      
      if (!mainSelect || !subSelect) continue;
      
      mainSelect.innerHTML = '<option value="">Loading...</option>';
      subSelect.innerHTML = '<option value="">Loading...</option>';
      mainSelect.disabled = true;
      subSelect.disabled = true;
      
      if (fpsSelect) {
        fpsSelect.innerHTML = '<option value="">Loading...</option>';
        fpsSelect.disabled = true;
      }
      if (bitrateSelect) {
        bitrateSelect.innerHTML = '<option value="">Loading...</option>';
        bitrateSelect.disabled = true;
      }
      if (protoSelect) {
        protoSelect.innerHTML = '<option value="">Loading...</option>';
        protoSelect.disabled = true;
      }
      
      try {
        const res = await fetch(`/api/devices/${cam.id}/resolution`);
        const result = await res.json();
        
        if (result.success) {
          this.populateResolutionSelect(mainSelect, result.main);
          this.populateResolutionSelect(subSelect, result.sub);
          
          if (fpsSelect && result.main && result.main.framerate !== undefined) {
            this.populateFpsSelect(fpsSelect, result.main.framerate);
          }
          if (bitrateSelect && result.main && result.main.bitrate !== undefined) {
            this.populateBitrateSelect(bitrateSelect, result.main.bitrate);
          }
          if (protoSelect && result.main && result.main.protocol !== undefined) {
            this.populateProtocolSelect(protoSelect, result.main.protocol);
          }
        } else {
          mainSelect.innerHTML = `<option value="">Error: ${result.message || 'Failed'}</option>`;
          subSelect.innerHTML = `<option value="">Error: ${result.message || 'Failed'}</option>`;
          if (fpsSelect) fpsSelect.innerHTML = '<option value="">Error</option>';
          if (bitrateSelect) bitrateSelect.innerHTML = '<option value="">Error</option>';
          if (protoSelect) protoSelect.innerHTML = '<option value="">Error</option>';
        }
      } catch (err) {
        console.error('[Resolution] Error fetching camera resolution:', cam.id, err);
        mainSelect.innerHTML = '<option value="">Error</option>';
        subSelect.innerHTML = '<option value="">Error</option>';
        if (fpsSelect) fpsSelect.innerHTML = '<option value="">Error</option>';
        if (bitrateSelect) bitrateSelect.innerHTML = '<option value="">Error</option>';
        if (protoSelect) protoSelect.innerHTML = '<option value="">Error</option>';
      }
    }
  },

  async loadNvrCamerasRecordingRanges(nvrId) {
    const nvrCameras = this.devices.filter(c => c.type === 'CAM' && c.parent_nvr_id === nvrId);
    for (const cam of nvrCameras) {
      const container = document.getElementById(`cam-range-${cam.id}`);
      if (!container) continue;
      
      if (!cam.is_online) {
        container.innerHTML = 'Rec Range: <span style="color: var(--text-muted)">N/A (Camera offline)</span>';
        continue;
      }
      
      try {
        const res = await fetch(`/api/devices/${cam.id}/recording-range`);
        const result = await res.json();
        
        if (result.success) {
          const isMock = '';
          const firstDate = result.first_rec.split(' ')[0];
          const lastDate = result.last_rec.split(' ')[0];
          container.innerHTML = `Rec Range: <strong style="color: var(--text-primary); font-size: 0.7rem;">${firstDate}</strong> to <strong style="color: var(--text-primary); font-size: 0.7rem;">${lastDate}</strong>${isMock}`;
        } else {
          container.innerHTML = `Rec Range: <span style="color: var(--text-muted);">${result.message || 'Error'}</span>`;
        }
      } catch (err) {
        console.error('[Range] Error fetching camera recording range:', cam.id, err);
        container.innerHTML = 'Rec Range: <span style="color: var(--text-muted);">Error</span>';
      }
    }
  },

  populateResolutionSelect(selectEl, streamData) {
    if (!selectEl || !streamData) return;
    
    const currentVal = `${streamData.width}x${streamData.height}`;
    const standardResolutions = [
      { value: '1920x1080', label: '1080p (1920x1080)' },
      { value: '1280x720', label: '720p (1280x720)' },
      { value: '704x576', label: 'D1 (704x576)' },
      { value: '640x480', label: 'VGA (640x480)' },
      { value: '352x288', label: 'CIF (352x288)' }
    ];
    
    let html = '';
    let found = false;
    standardResolutions.forEach(res => {
      const isSelected = res.value === currentVal ? 'selected' : '';
      if (isSelected) found = true;
      html += `<option value="${res.value}" ${isSelected}>${res.label}</option>`;
    });
    
    if (!found && streamData.width && streamData.height) {
      html = `<option value="${currentVal}" selected>Custom (${currentVal})</option>` + html;
    }
    
    selectEl.innerHTML = html;
    selectEl.disabled = false;
  },

  async changeCameraResolution(camId, streamType, resolution) {
    if (!resolution) return;
    const [width, height] = resolution.split('x').map(Number);
    const selectEl = document.getElementById(`cam-${camId}-${streamType}-res`);
    if (selectEl) selectEl.disabled = true;
    
    this.showToast(`Updating camera resolution to ${resolution}...`, 'info');
    
    try {
      const res = await fetch(`/api/devices/${camId}/resolution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_type: streamType, width, height })
      });
      const result = await res.json();
      if (result.success) {
        this.showToast(result.message || 'Resolution updated successfully!', 'success');
      } else {
        this.showToast(result.message || 'Failed to update resolution', 'error');
        // reload
        const cam = this.devices.find(d => d.id === camId);
        if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
      }
    } catch (err) {
      console.error('[Resolution] Change failed:', err);
      this.showToast('Connection error changing resolution', 'error');
      const cam = this.devices.find(d => d.id === camId);
      if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
    } finally {
      if (selectEl) selectEl.disabled = false;
    }
  },

  populateFpsSelect(selectEl, currentFps) {
    if (!selectEl) return;
    const fpsOptions = [30, 25, 20, 15, 12, 10, 5];
    let html = '';
    let found = false;
    fpsOptions.forEach(fps => {
      const isSelected = fps === currentFps ? 'selected' : '';
      if (isSelected) found = true;
      html += `<option value="${fps}" ${isSelected}>${fps} fps</option>`;
    });
    if (!found && currentFps) {
      html = `<option value="${currentFps}" selected>${currentFps} fps (Custom)</option>` + html;
    }
    selectEl.innerHTML = html;
    selectEl.disabled = false;
  },

  populateBitrateSelect(selectEl, currentBitrate) {
    if (!selectEl) return;
    const bitrateOptions = [8192, 4096, 2048, 1024, 512, 256];
    let html = '';
    let found = false;
    bitrateOptions.forEach(br => {
      const isSelected = br === currentBitrate ? 'selected' : '';
      if (isSelected) found = true;
      const label = br >= 1024 ? `${br / 1024} Mbps` : `${br} Kbps`;
      html += `<option value="${br}" ${isSelected}>${label}</option>`;
    });
    if (!found && currentBitrate) {
      const label = currentBitrate >= 1024 ? `${currentBitrate / 1024} Mbps` : `${currentBitrate} Kbps`;
      html = `<option value="${currentBitrate}" selected>${label} (Custom)</option>` + html;
    }
    selectEl.innerHTML = html;
    selectEl.disabled = false;
  },

  populateProtocolSelect(selectEl, currentProto) {
    if (!selectEl) return;
    const protoOptions = ['RTSP', 'HTTP', 'AUTO', 'SRT'];
    let html = '';
    let found = false;
    protoOptions.forEach(p => {
      const isSelected = p.toUpperCase() === (currentProto || '').toUpperCase() ? 'selected' : '';
      if (isSelected) found = true;
      html += `<option value="${p}" ${isSelected}>${p}</option>`;
    });
    if (!found && currentProto) {
      html = `<option value="${currentProto}" selected>${currentProto}</option>` + html;
    }
    selectEl.innerHTML = html;
    selectEl.disabled = false;
  },

  async changeCameraFramerate(camId, framerate) {
    if (!framerate) return;
    const selectEl = document.getElementById(`cam-${camId}-main-fps`);
    if (selectEl) selectEl.disabled = true;
    
    this.showToast(`Updating camera framerate to ${framerate} fps...`, 'info');
    
    try {
      const res = await fetch(`/api/devices/${camId}/resolution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_type: 'main', framerate: parseInt(framerate) })
      });
      const result = await res.json();
      if (result.success) {
        this.showToast(result.message || 'Framerate updated successfully!', 'success');
      } else {
        this.showToast(result.message || 'Failed to update framerate', 'error');
        const cam = this.devices.find(d => d.id === camId);
        if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
      }
    } catch (err) {
      console.error('[Framerate] Change failed:', err);
      this.showToast('Connection error changing framerate', 'error');
      const cam = this.devices.find(d => d.id === camId);
      if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
    } finally {
      if (selectEl) selectEl.disabled = false;
    }
  },

  async changeCameraBitrate(camId, bitrate) {
    if (!bitrate) return;
    const selectEl = document.getElementById(`cam-${camId}-main-bitrate`);
    if (selectEl) selectEl.disabled = true;
    
    const label = bitrate >= 1024 ? `${bitrate / 1024} Mbps` : `${bitrate} Kbps`;
    this.showToast(`Updating camera bitrate to ${label}...`, 'info');
    
    try {
      const res = await fetch(`/api/devices/${camId}/resolution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_type: 'main', bitrate: parseInt(bitrate) })
      });
      const result = await res.json();
      if (result.success) {
        this.showToast(result.message || 'Bitrate updated successfully!', 'success');
      } else {
        this.showToast(result.message || 'Failed to update bitrate', 'error');
        const cam = this.devices.find(d => d.id === camId);
        if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
      }
    } catch (err) {
      console.error('[Bitrate] Change failed:', err);
      this.showToast('Connection error changing bitrate', 'error');
      const cam = this.devices.find(d => d.id === camId);
      if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
    } finally {
      if (selectEl) selectEl.disabled = false;
    }
  },

  async changeCameraProtocol(camId, protocol) {
    if (!protocol) return;
    const selectEl = document.getElementById(`cam-${camId}-main-proto`);
    if (selectEl) selectEl.disabled = true;
    
    this.showToast(`Updating camera transport protocol to ${protocol}...`, 'info');
    
    try {
      const res = await fetch(`/api/devices/${camId}/resolution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_type: 'main', protocol: protocol })
      });
      const result = await res.json();
      if (result.success) {
        this.showToast(result.message || 'Protocol updated successfully!', 'success');
      } else {
        this.showToast(result.message || 'Failed to update protocol', 'error');
        const cam = this.devices.find(d => d.id === camId);
        if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
      }
    } catch (err) {
      console.error('[Protocol] Change failed:', err);
      this.showToast('Connection error changing protocol', 'error');
      const cam = this.devices.find(d => d.id === camId);
      if (cam && cam.parent_nvr_id) this.loadNvrCamerasResolutions(cam.parent_nvr_id);
    } finally {
      if (selectEl) selectEl.disabled = false;
    }
  },

  async batchChangeCameraResolution(nvrId, resolution) {
    if (!resolution) return;
    const [width, height] = resolution.split('x').map(Number);
    
    const confirmChange = confirm(`Are you sure you want to change ALL cameras mainstream resolution under this NVR to ${resolution}?`);
    if (!confirmChange) return;
    
    this.showToast(`Batch configuring cameras under NVR to ${resolution}...`, 'info');
    
    try {
      const res = await fetch(`/api/devices/nvr/${nvrId}/batch-resolution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_type: 'main', width, height })
      });
      const result = await res.json();
      if (result.success) {
        if (result.overall_success) {
          this.showToast('All camera resolutions updated successfully!', 'success');
        } else {
          console.warn('[Resolution] Batch update completed with some errors:', result.results);
          const failures = result.results.filter(r => !r.success);
          failures.forEach(f => {
            console.error(`- Camera "${f.cam_name}" failed: ${f.message}`);
          });
          this.showToast('Batch complete with some errors. Check Developer Console (F12) for details.', 'warning');
        }
        // reload NVR camera resolutions
        this.loadNvrCamerasResolutions(nvrId);
      } else {
        this.showToast(result.message || 'Batch update failed', 'error');
      }
    } catch (err) {
      console.error('[Resolution] Batch update failed:', err);
      this.showToast('Connection error performing batch update', 'error');
    }
  },

  async loadNvrTimeDifferences() {
    const nvrs = this.devices.filter(d => d.type === 'NVR');
    for (const nvr of nvrs) {
      const cell = document.getElementById(`nvr-time-diff-${nvr.id}`);
      if (!cell) continue;
      
      if (!nvr.is_online) {
        cell.innerHTML = '<span style="color:var(--text-muted)">N/A</span>';
        continue;
      }
      
      cell.innerHTML = '<span style="font-size:0.75rem; color:var(--text-secondary)">Loading...</span>';
      
      try {
        const res = await fetch(`/api/devices/${nvr.id}/nvr-time`);
        const result = await res.json();
        
        if (result.success) {
          const diff = result.diff_seconds;
          let badgeClass = 'recording-ok';
          let diffStr = '';
          
          if (Math.abs(diff) <= 5) {
            diffStr = 'Synced';
            badgeClass = 'recording-ok';
          } else {
            const prefix = diff > 0 ? '+' : '';
            const absSecs = Math.abs(diff);
            if (absSecs < 60) {
              diffStr = `${prefix}${diff}s`;
            } else {
              const m = Math.floor(absSecs / 60);
              const s = Math.round(absSecs % 60);
              diffStr = `${prefix}${m}m ${s}s`;
            }
            
            badgeClass = absSecs > 60 ? 'recording-issue' : 'recording-unknown';
          }
          
          const isMock = '';
          
          cell.innerHTML = `<span class="device-card-badge ${badgeClass}" title="NVR Time: ${result.nvr_time}\nNTP Time: ${result.ntp_time}">${diffStr}</span>${isMock}`;
        } else {
          cell.innerHTML = `<span class="device-card-badge recording-issue" title="${result.message || 'Error'}">Error</span>`;
        }
      } catch (err) {
        console.error('[Time] Failed to fetch time difference for NVR', nvr.id, err);
        cell.innerHTML = '<span class="device-card-badge recording-issue">Error</span>';
      }
    }
  },

  async syncNvrTime(nvrId) {
    this.showToast('Configuring and syncing NVR time with NTP server...', 'info');
    const cell = document.getElementById(`nvr-time-diff-${nvrId}`);
    if (cell) cell.innerHTML = '<span style="font-size:0.75rem; color:var(--text-secondary)">Syncing...</span>';
    
    try {
      const res = await fetch(`/api/devices/${nvrId}/sync-time`, { method: 'POST' });
      const result = await res.json();
      
      if (result.success) {
        this.showToast(result.message || 'NVR Clock successfully synced!', 'success');
        setTimeout(() => {
          this.loadNvrTimeDifferences();
        }, 1500);
      } else {
        this.showToast(result.message || 'Failed to sync NVR clock', 'error');
        this.loadNvrTimeDifferences();
      }
    } catch (err) {
      console.error('[Time] Sync request failed:', err);
      this.showToast('Connection error triggering time sync', 'error');
      this.loadNvrTimeDifferences();
    }
  },

  // Live Camera preview modal state variables
  liveStreamInterval: null,
  liveStreamCamId: null,
  liveStreamName: null,

  openCameraLiveModal(camId, name) {
    this.liveStreamCamId = camId;
    this.liveStreamName = name;
    
    const overlay = document.getElementById('liveStreamModalOverlay');
    const title = document.getElementById('liveStreamModalTitle');
    const img = document.getElementById('liveStreamImg');
    const loading = document.getElementById('liveStreamLoading');
    const errorOverlay = document.getElementById('liveStreamErrorOverlay');
    const fpsSelect = document.getElementById('liveStreamFps');
    
    if (!overlay || !img) return;
    
    title.textContent = `Live Camera Feed: ${name}`;
    img.src = '';
    if (loading) loading.style.display = 'flex';
    if (errorOverlay) errorOverlay.style.display = 'none';
    
    overlay.classList.add('active');
    
    // Default refresh rate: 2 frames/sec (500ms)
    const intervalMs = fpsSelect ? parseInt(fpsSelect.value) : 500;
    this.startLiveStreamRefresh(intervalMs);
  },

  startLiveStreamRefresh(ms) {
    this.clearLiveStreamRefresh();
    
    // Initial fetch
    this.refreshLiveStreamSnapshot();
    
    if (ms > 0) {
      this.liveStreamInterval = setInterval(() => {
        this.refreshLiveStreamSnapshot();
      }, ms);
    }
  },

  clearLiveStreamRefresh() {
    if (this.liveStreamInterval) {
      clearInterval(this.liveStreamInterval);
      this.liveStreamInterval = null;
    }
  },

  refreshLiveStreamSnapshot() {
    const img = document.getElementById('liveStreamImg');
    if (!img || !this.liveStreamCamId) return;
    
    // Add cache buster timestamp
    img.src = `/api/devices/${this.liveStreamCamId}/snapshot?t=${Date.now()}`;
  },

  changeLiveStreamFps(val) {
    const ms = parseInt(val);
    this.startLiveStreamRefresh(ms);
  },

  closeLiveStreamModal() {
    this.clearLiveStreamRefresh();
    this.liveStreamCamId = null;
    this.liveStreamName = null;
    
    const overlay = document.getElementById('liveStreamModalOverlay');
    const img = document.getElementById('liveStreamImg');
    if (overlay) overlay.classList.remove('active');
    if (img) img.src = '';
  },

  handleLiveStreamError() {
    const loading = document.getElementById('liveStreamLoading');
    const errorOverlay = document.getElementById('liveStreamErrorOverlay');
    
    if (loading) loading.style.display = 'none';
    if (errorOverlay) errorOverlay.style.display = 'flex';
  },

  // Format integer to Bangladesh currency format (Lakhs)
  formatCurrency(value) {
    if (value === null || value === undefined) return '--';
    // Format as ৳XX,XX,XXX or simple comma separation
    return '৳ ' + Number(value).toLocaleString('en-IN');
  },

  // Store chart instances globally on App object to reuse/destroy them on refresh
  networkStatusChart: null,
  pingSummaryChart: null,
  uptimeStart: Date.now(), // timestamp when page loads

  updateNewDashboard() {
    if (!document.getElementById('db-total-nodes')) return; // not on dashboard view or elements missing

    const devices = this.devices || [];

    // 1. Calculate General Counts
    const total = devices.length;
    const online = devices.filter(d => d.is_online).length;
    const down = devices.filter(d => !d.is_online).length;
    
    // Warnings are NVRs which are online but not recording
    const warning = devices.filter(d => d.type === 'NVR' && d.is_online && !d.nvr_recording).length;

    const onlinePct = total > 0 ? ((online / total) * 100).toFixed(1) : '0.0';
    const downPct = total > 0 ? ((down / total) * 100).toFixed(1) : '0.0';
    const warningPct = total > 0 ? ((warning / total) * 100).toFixed(1) : '0.0';

    // Update Top Stats
    document.getElementById('db-total-nodes').textContent = total;
    document.getElementById('db-online-nodes').textContent = online;
    document.getElementById('db-online-pct').textContent = `${onlinePct}%`;
    document.getElementById('db-down-nodes').textContent = down;
    document.getElementById('db-down-pct').textContent = `${downPct}%`;
    document.getElementById('db-warning-nodes').textContent = warning;
    document.getElementById('db-warning-pct').textContent = `${warningPct}%`;

    // 2. Device Type Counts & Sub-counters
    const types = ['ATM', 'NVR', 'CAM', 'CRM', 'Router', 'Server'];
    types.forEach(t => {
      const typeDevices = devices.filter(d => d.type === t);
      const typeCount = typeDevices.length;
      const typeOnline = typeDevices.filter(d => d.is_online).length;
      
      const countEl = document.getElementById(`sc-${t.toLowerCase()}-count`);
      const onlineEl = document.getElementById(`sc-${t.toLowerCase()}-online`);
      
      if (countEl) countEl.textContent = typeCount;
      if (onlineEl) onlineEl.textContent = `${typeOnline} Online`;
    });

    // Update bottom total counters
    const bottomAtmTotal = document.getElementById('bottom-atm-total');
    if (bottomAtmTotal) bottomAtmTotal.textContent = devices.filter(d => d.type === 'ATM').length;
    const bottomNvrTotal = document.getElementById('bottom-nvr-total');
    if (bottomNvrTotal) bottomNvrTotal.textContent = devices.filter(d => d.type === 'NVR').length;

    // 3. Populate Recent Nodes Table
    // Get up to 8 most recently updated nodes
    const sortedDevices = [...devices].sort((a, b) => {
      const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return bTime - aTime;
    }).slice(0, 8);

    const recentTbody = document.getElementById('db-recent-nodes-tbody');
    if (recentTbody) {
      recentTbody.innerHTML = '';
      sortedDevices.forEach(d => {
        const pingLoss = d.is_online ? `${d.last_packet_loss || 0}%` : '100%';
        const responseTime = d.is_online ? `${Math.round(d.last_latency || 0)} ms` : '-';
        let statusBadge = '';
        if (d.is_online) {
          if (d.type === 'NVR' && !d.nvr_recording) {
            statusBadge = '<span class="device-card-badge recording-issue">Stop / Issue</span>';
          } else {
            statusBadge = '<span class="device-card-badge recording-ok">Online</span>';
          }
        } else {
          statusBadge = '<span class="device-card-badge recording-issue">Down</span>';
        }

        recentTbody.innerHTML += `
          <tr>
            <td><strong>${d.type}</strong></td>
            <td><strong>${d.name}</strong><br><span style="color: var(--text-muted); font-size: 0.7rem;">${d.location || '--'}</span></td>
            <td><span class="device-card-ip">${d.ip}</span></td>
            <td>${statusBadge}</td>
            <td>${pingLoss}</td>
            <td>${responseTime}</td>
            <td>${d.last_ping_time || '--'}</td>
          </tr>
        `;
      });
    }

    // 4. Critical Alerts list in panel
    // Find devices that are offline or have NVR issues
    const criticalDevices = devices.filter(d => !d.is_online || (d.type === 'NVR' && d.is_online && !d.nvr_recording));
    const critCountEl = document.getElementById('critical-alerts-count');
    if (critCountEl) critCountEl.textContent = criticalDevices.length;
    
    const critListEl = document.getElementById('db-critical-alerts-list');
    if (critListEl) {
      critListEl.innerHTML = '';
      if (criticalDevices.length === 0) {
        critListEl.innerHTML = '<div style="color: var(--accent-green); font-size: 0.8rem; text-align: center; padding: 1rem;">No critical alerts. System OK!</div>';
      } else {
        criticalDevices.forEach(d => {
          let text = '';
          if (!d.is_online) {
            text = `${d.type} ${d.name} (${d.ip}) is Offline.`;
          } else {
            text = `NVR ${d.name} is Online but Recording has Stopped.`;
          }
          critListEl.innerHTML += `
            <div class="db-alert-item critical">
              <span>🚨 ${text}</span>
              <span style="color: var(--text-muted); font-size: 0.7rem;">${d.last_ping_time || 'Just now'}</span>
            </div>
          `;
        });
      }
    }

    // 5. Top Alerts List
    const topAlertsEl = document.getElementById('db-top-alerts-list');
    if (topAlertsEl) {
      topAlertsEl.innerHTML = '';
      const activeAlerts = criticalDevices.slice(0, 5);
      if (activeAlerts.length === 0) {
        topAlertsEl.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 1rem;">No active alerts</div>';
      } else {
        activeAlerts.forEach(d => {
          const typeLabel = !d.is_online ? 'Ping Loss 100%' : 'Recording Stopped';
          topAlertsEl.innerHTML += `
            <div style="display: flex; flex-direction: column; gap: 0.15rem; font-size: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 0.4rem; width: 100%;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: var(--accent-red);">● ${d.name}</span>
                <span style="color: var(--text-muted); font-size: 0.65rem;">${d.last_ping_time ? d.last_ping_time.split(',')[1] || d.last_ping_time : '--'}</span>
              </div>
              <span style="color: var(--text-secondary); font-size: 0.7rem;">${typeLabel}</span>
            </div>
          `;
        });
      }
    }

    // 6. ATM Cash status
    const atmTbody = document.getElementById('db-atm-cash-tbody');
    if (atmTbody) {
      atmTbody.innerHTML = '';
      const atms = devices.filter(d => d.type === 'ATM');
      if (atms.length === 0) {
        atmTbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color: var(--text-muted);">No ATM devices</td></tr>';
      } else {
        atms.slice(0, 3).forEach(d => {
          const bal = d.atm_balance !== null ? this.formatCurrency(d.atm_balance) : '৳ --';
          atmTbody.innerHTML += `
            <tr>
              <td><strong>${d.name}</strong></td>
              <td style="color: var(--text-muted);">${d.location || '--'}</td>
              <td style="text-align: right; color: var(--accent-amber); font-weight: 500;">${bal}</td>
            </tr>
          `;
        });
      }
    }

    // 7. NVR Last record
    const nvrTbody = document.getElementById('db-nvr-record-tbody');
    if (nvrTbody) {
      nvrTbody.innerHTML = '';
      const nvrs = devices.filter(d => d.type === 'NVR');
      if (nvrs.length === 0) {
        nvrTbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color: var(--text-muted);">No NVR devices</td></tr>';
      } else {
        nvrs.slice(0, 3).forEach(d => {
          const lastRec = d.nvr_last_recording ? this.getRelativeTime(d.nvr_last_recording) : 'N/A';
          nvrTbody.innerHTML += `
            <tr>
              <td><strong>${d.name}</strong></td>
              <td style="color: var(--text-muted);">${d.location || '--'}</td>
              <td style="text-align: right; color: var(--accent-red); font-weight: 500;">${lastRec}</td>
            </tr>
          `;
        });
      }
    }

    // Update dynamic settings values on dashboard
    if (this.settings) {
      const emailInterval = this.settings.email_alert_after_minutes || 60;
      const smsInterval = this.settings.sms_alert_after_minutes || 120;
      const pingInterval = this.settings.ping_interval_minutes || 5;

      const emailStatusEl = document.getElementById('db-email-status');
      if (emailStatusEl) {
        emailStatusEl.textContent = `● Active (${emailInterval} Min)`;
      }
      const smsStatusEl = document.getElementById('db-sms-status');
      if (smsStatusEl) {
        smsStatusEl.textContent = `● Active (${smsInterval} Min)`;
      }
      const pingIntervalEl = document.getElementById('db-ping-interval');
      if (pingIntervalEl) {
        pingIntervalEl.textContent = `${pingInterval} Minutes`;
      }
    }

    // 8. Server Time
    const serverTimeEl = document.getElementById('db-server-time');
    if (serverTimeEl) {
      serverTimeEl.textContent = new Date().toLocaleString();
    }

    // 9. Initialize / Update Chart.js Charts
    this.renderCharts(online, down, warning);
  },

  renderCharts(online, down, warning) {
    if (typeof Chart === 'undefined') return; // library not loaded yet

    // Donut Chart: Network Status
    const donutCtx = document.getElementById('networkStatusChart');
    if (donutCtx) {
      if (this.networkStatusChart) {
        this.networkStatusChart.destroy();
      }

      this.networkStatusChart = new Chart(donutCtx, {
        type: 'doughnut',
        data: {
          labels: ['Online', 'Down', 'Warning'],
          datasets: [{
            data: [online, down, warning],
            backgroundColor: ['#00d97e', '#ff4757', '#ffb84d'],
            borderWidth: 0,
            hoverOffset: 4
          }]
        },
        options: {
          cutout: '70%',
          plugins: {
            legend: { display: false }
          },
          responsive: true,
          maintainAspectRatio: false
        }
      });

      // Update Legend percentages
      const legendEl = document.getElementById('donutLegend');
      if (legendEl) {
        const total = online + down + warning;
        const onlinePct = total > 0 ? ((online / total) * 100).toFixed(1) : 0;
        const downPct = total > 0 ? ((down / total) * 100).toFixed(1) : 0;
        const warningPct = total > 0 ? ((warning / total) * 100).toFixed(1) : 0;

        legendEl.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span><span class="status-dot online" style="display:inline-block; margin-right:4px;"></span> Online</span>
            <strong>${online} (${onlinePct}%)</strong>
          </div>
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span><span class="status-dot offline" style="display:inline-block; margin-right:4px;"></span> Down</span>
            <strong>${down} (${downPct}%)</strong>
          </div>
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span><span class="status-dot warning" style="display:inline-block; margin-right:4px; background:var(--accent-amber);"></span> Warning</span>
            <strong>${warning} (${warningPct}%)</strong>
          </div>
        `;
      }
    }

    // Line Chart: Ping Response Summary
    const lineCtx = document.getElementById('pingSummaryChart');
    if (lineCtx) {
      if (this.pingSummaryChart) {
        this.pingSummaryChart.destroy();
      }

      // Generate realistic mock timestamps for the last 6 iterations (last 30 minutes)
      const labels = [];
      const now = new Date();
      for (let i = 5; i >= 0; i--) {
        const t = new Date(now.getTime() - i * 5 * 60000);
        labels.push(`${t.getHours().toString().padStart(2, '0')}:${t.getMinutes().toString().padStart(2, '0')}`);
      }

      // Generate success rate based on real stats
      const total = online + down;
      const realSuccessPct = total > 0 ? Math.round((online / total) * 100) : 100;
      const successData = [realSuccessPct, realSuccessPct - 2, realSuccessPct, realSuccessPct + 1, realSuccessPct - 1, realSuccessPct];
      const lossData = successData.map(val => 100 - val);

      this.pingSummaryChart = new Chart(lineCtx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Success %',
              data: successData,
              borderColor: '#00d97e',
              backgroundColor: 'rgba(0, 217, 126, 0.05)',
              fill: true,
              tension: 0.4,
              borderWidth: 2,
              pointRadius: 2
            },
            {
              label: 'Packet Loss %',
              data: lossData,
              borderColor: '#ff4757',
              backgroundColor: 'rgba(255, 71, 87, 0.05)',
              fill: true,
              tension: 0.4,
              borderWidth: 2,
              pointRadius: 2
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              labels: {
                color: '#9ca3af',
                boxWidth: 10,
                font: { size: 9 }
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: '#6b7280', font: { size: 8 } }
            },
            y: {
              min: 0,
              max: 100,
              grid: { color: 'rgba(255, 255, 255, 0.03)' },
              ticks: { color: '#6b7280', font: { size: 8 } }
            }
          }
        }
      });
    }
  },

  startUptimeCounter() {
    setInterval(() => {
      const diffMs = Date.now() - this.uptimeStart;
      const secs = Math.floor((diffMs / 1000) % 60);
      const mins = Math.floor((diffMs / 60000) % 60);
      const hrs = Math.floor((diffMs / 3600000) % 24);
      const days = Math.floor(diffMs / 86400000);
      
      const uptimeStr = `${days.toString().padStart(2, '0')}:${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
      const el = document.getElementById('db-uptime');
      if (el) el.textContent = uptimeStr;
    }, 1000);
  },

  filterNvrWarnings: false,

  showWarningNvrDetails() {
    this.filterNvrWarnings = true;
    this.switchView('nvr');
    this.renderNvrTable();
  },

  startClock() {
    const clock = document.getElementById('headerClock');
    setInterval(() => {
      const now = new Date();
      clock.textContent = now.toLocaleTimeString();
    }, 1000);
  }
};

// Start the application when DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
