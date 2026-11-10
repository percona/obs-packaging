/* PPG QA dashboard: renders /data.json (see collect.py) as the overview
 * (#) or a major's detail page (#pg18). Re-fetches the data every minute. */
(function () {
  'use strict';
  var data = null;
  var filter = 'all';
  var app = document.getElementById('app');

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function link(url, text, cls) {
    if (!url) return '<span class="' + (cls || '') + '">' + text + '</span>';
    return '<a class="' + (cls || '') + '" href="' + esc(url) + '" target="_blank" rel="noopener">' + text + '</a>';
  }
  var CHECK = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>';
  var CROSS = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>';

  // "38 min", "2 h 05 min": time elapsed since iso
  function duration(iso) {
    var mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    if (mins < 60) return mins + ' min';
    return Math.floor(mins / 60) + ' h ' + ('0' + (mins % 60)).slice(-2) + ' min';
  }
  function ago(iso) {
    var mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    var h = Math.floor(mins / 60);
    return h + ' h ' + (mins % 60) + ' min ago';
  }

  function header(title, subtitle) {
    var stale = data.error ? ' stale' : '';
    return '<header class="top"><div><h1>' + title + '</h1><p>' + subtitle + '</p></div>' +
      '<div class="header-side">' +
      '<span class="live' + stale + '"><span class="dot" aria-hidden="true"></span>' +
      (data.generated_at ? 'Live · updated ' + esc(ago(data.generated_at)) : 'Waiting for data') + '</span>' +
      '<span class="muted" style="font-size:13px">Refreshes every ' + esc(data.refresh_minutes || 10) + ' min</span>' +
      (data.demo ? '<span class="tag-demo">Demo · sample data</span>' : '') +
      '</div></header>' +
      (data.error ? '<div class="alert" role="alert">The latest refresh failed (' + esc(data.error) +
        '). Showing the last good data.</div>' : '');
  }

  function statusChip(m) {
    if (m.status === 'pass') return '<span class="chip pass">' + CHECK + 'All passing</span>';
    if (m.status === 'fail') return '<span style="display:inline-flex;gap:6px;flex-wrap:wrap;align-items:center"><span class="chip fail">' +
      esc(m.failing) + ' failing</span><span class="badge-new">' + esc(m.new) + ' new</span></span>';
    if (m.status === 'known') return '<span class="chip known">' + esc(m.failing) + ' failing · all known</span>';
    if (m.status === 'running') return '<span class="chip running">Running · ' + esc(m.progress) + '</span>';
    if (m.status === 'queued') return '<span class="chip queued">Queued</span>';
    return '<span class="chip none">No runs yet</span>';
  }

  // KNOWN · PG-1234, linking to the ticket
  function knownBadge(f) {
    var text = 'KNOWN · ' + esc(f.ticket);
    if (!f.ticket_url) return '<span class="badge-known">' + text + '</span>';
    return '<a class="badge-known" href="' + esc(f.ticket_url) + '" target="_blank" rel="noopener" title="Open ' +
      esc(f.ticket) + '">' + text + ' ↗</a>';
  }

  var KIND_TEXT = { pass: 'all passing', fail: 'new failures', known: 'known failures only', running: 'running', queued: 'queued' };
  function runSquare(r) {
    var inner = r.kind === 'pass' ? CHECK : r.kind === 'fail' ? CROSS : r.kind === 'known' ? 'K' : r.kind === 'queued' ? '⋯' : '…';
    var label = esc(r.date) + ': ' + KIND_TEXT[r.kind];
    return '<a class="sq ' + esc(r.kind) + '" href="' + esc(r.url) + '" target="_blank" rel="noopener" title="' + label +
      '" aria-label="' + label + '">' + inner + '</a>';
  }

  function overview() {
    var h = header('PPG Nightly QA', 'OBS staging · ppg:staging:14 – 19 · one major per night, 02:00 UTC (Mon PG 14 → Sat PG 19)');
    // every nightly in progress, then the ones waiting to start
    (data.running || []).forEach(function (run) {
      var pct = run.total ? Math.round(run.done * 100 / run.total) : 0;
      h += '<section class="running" aria-label="Run in progress"><span class="label">Running now</span>' +
        '<span class="what">PG ' + esc(run.major) + ' nightly' + (run.rerun ? ' (re-run)' : '') + '</span>' +
        '<div class="bar" role="img" aria-label="' + esc(run.done) + ' of ' + esc(run.total) + ' builds done"><div style="width:' + pct + '%"></div></div>' +
        '<span class="mono" style="font-size:14px">' + esc(run.done) + ' / ' + esc(run.total) + ' done</span>' +
        (run.failing ? '<span class="bad">' + esc(run.failing) + ' failing so far</span>' : '<span class="ok">0 failing so far</span>') +
        '<span class="muted" style="font-size:14px">' + link(run.url, 'started ' + esc(duration(run.since)) + ' ago') + '</span></section>';
    });
    if ((data.queued || []).length) {
      h += '<section class="queued" aria-label="Runs waiting to start"><span class="label">Queued</span>' +
        data.queued.map(function (q) {
          return '<span>' + link(q.url, 'PG ' + esc(q.major) + ' nightly' + (q.rerun ? ' (re-run)' : '')) +
            ' <span class="muted">· waiting ' + esc(duration(q.since)) + '</span></span>';
        }).join('') +
        '<span class="muted" style="font-size:13px">Nightlies run one at a time: these start when the running one ends.</span></section>';
    }
    h += '<section class="card" aria-labelledby="majors-title"><div class="card-head"><h2 id="majors-title">Majors</h2>' +
      '<span>Last 5 runs: oldest → newest (nightly and manual)</span></div><div class="scroll"><div class="grid-majors">' +
      ['Major', 'Status', 'Failing', 'Last run', 'Run time', 'Last 5 runs', ''].map(function (t) { return '<span class="grid-head">' + t + '</span>'; }).join('');
    data.majors.forEach(function (m) {
      var cells = [
        '<span class="major-name">PG ' + esc(m.major) + '</span>',
        '<div>' + statusChip(m) + '</div>',
        '<span class="mono">' + (m.runs.length ? esc(m.failing) + ' / ' + esc(m.total) : '–') + '</span>',
        '<span>' + (m.last_run_url ? link(m.last_run_url, esc(m.last_run)) : esc(m.last_run || '–')) + '</span>',
        '<div class="stack"><span class="mono">' + esc(m.runtime || '–') + '</span>' +
          (m.slow ? '<span class="slow">+' + esc(m.slow_pct) + '% vs median ' + esc(m.median) + '</span>'
                  : (m.median && m.median !== '–' ? '<span class="muted" style="font-size:12px">median ' + esc(m.median) + '</span>' : '')) + '</div>',
        '<div class="runs">' + m.runs.map(runSquare).join('') + '</div>',
        m.runs.length ? '<a class="details-link" href="#pg' + esc(m.major) + '">Details →</a>' : '<span></span>'
      ];
      h += cells.map(function (c) { return c.replace(/^<(\w+)( class="([^"]*)")?/, function (_, tag, __, cls) { return '<' + tag + ' class="grid-row ' + (cls || '') + '"'; }); }).join('');
    });
    h += '</div></div><div class="legend">' +
      '<span><i style="background:var(--pass)"></i>All passing</span>' +
      '<span><i style="background:var(--known)"></i>Known failures only (ticket open)</span>' +
      '<span><i style="background:var(--fail)"></i>New failures</span>' +
      '<span><i style="border:2px dashed var(--run)"></i>Running</span>' +
      '<span><i style="border:2px dashed #9AA1AD"></i>Queued</span>' +
      '<span>Run time flagged when ≥ 50% slower than the median of the major\'s last 5 runs</span></div></section>';

    var all = data.failures, nNew = all.filter(function (f) { return f.is_new; }).length;
    var shown = all.filter(function (f) { return filter === 'all' || (filter === 'new') === f.is_new; });
    h += '<section class="card" aria-labelledby="failing-title"><div class="card-head"><h2 id="failing-title">Failing now</h2>' +
      '<div class="filters" role="group" aria-label="Filter failures">' +
      [['all', 'All · ' + all.length], ['new', 'New · ' + nNew], ['known', 'Known · ' + (all.length - nNew)]].map(function (b) {
        return '<button type="button" data-filter="' + b[0] + '" aria-pressed="' + (filter === b[0]) + '">' + b[1] + '</button>';
      }).join('') + '</div></div>';
    if (!shown.length) h += '<p class="empty">' + (all.length ? 'Nothing in this filter.' : 'Nothing failing.') + '</p>';
    shown.forEach(function (f) {
      h += '<article class="failure"><div class="tag">' + (f.is_new ? '<span class="badge-new">NEW · no ticket</span>' : knownBadge(f)) + '</div>' +
        '<span class="major">PG ' + esc(f.major) + '</span>' +
        '<div class="what"><b>' + esc(f.title) + '</b><span>' + esc(f.job) + ' · ' + esc(f.platforms) + '</span></div>' +
        '<div class="since stack"><span class="small-label">Failing since</span><span>' + esc(f.since) + '</span></div>' +
        link(f.build_url, 'Jenkins ' + esc(f.build) + ' →', 'details-link') + '</article>';
    });
    h += '</section><footer><span>Data: GitHub Actions (OBS QA runs) + Jenkins</span>' +
      '<span>Known failures: .github/qa-known-failures.yaml</span>' +
      (data.repo ? '<span>' + link('https://github.com/' + data.repo + '/actions', esc(data.repo)) + '</span>' : '') + '</footer>';
    return h;
  }

  function detail(major) {
    var d = data.details[major];
    if (!d) return '<a class="back" href="#">← All majors</a><p class="empty">No runs for PG ' + esc(major) + ' yet.</p>';
    var h = '<a class="back" href="#">← All majors</a>' +
      header('PG ' + esc(major), 'ppg:staging:' + esc(major) + ' · nightly 02:00 UTC');
    var known = d.known_tickets.length ? ' · ' + (d.failing - d.new) + ' known (' + d.known_tickets.map(esc).join(', ') + ')' : '';
    h += '<section class="summary" aria-label="Summary">' +
      '<div class="card"><span class="small-label">Failing (last run)</span><span class="big" style="color:' + (d.failing ? 'var(--fail)' : 'var(--pass-ink)') + '">' +
        esc(d.failing) + ' / ' + esc(d.total) + '</span><span class="muted" style="font-size:13px">' + esc(d.new) + ' new' + known + '</span></div>' +
      '<div class="card"><span class="small-label">Last run</span><span class="mid">' + esc(d.last_run) + '</span><span class="muted" style="font-size:13px">' + esc(d.last_run_window) + '</span></div>' +
      '<div class="card"><span class="small-label">Run time</span><span class="big">' + esc(d.runtime) + '</span>' +
        (d.slow ? '<span class="slow">+' + esc(d.slow_pct) + '% vs median ' + esc(d.median) + '</span>' : '<span class="muted" style="font-size:13px">median ' + esc(d.median) + '</span>') + '</div>' +
      '<div class="card"><span class="small-label">Slowest build</span>' +
        (d.slowest ? '<span style="font-size:18px;font-weight:600">' + esc(d.slowest.name) + '</span><span class="muted" style="font-size:13px">' + esc(d.slowest.duration) +
          (d.slowest.usual ? ' · usually ' + esc(d.slowest.usual) : '') + '</span>' : '<span class="muted">Not available (Jenkins)</span>') + '</div></section>';

    var max = Math.max.apply(null, d.runtimes.map(function (r) { return r.minutes; }).concat([d.median_minutes, 1]));
    var scale = 180 / max;
    h += '<section class="card" aria-labelledby="rt-title"><div class="card-head"><h2 id="rt-title">Run time, last 5 runs</h2>' +
      '<span>From the run\'s start to its last build finishing · dashed line: median</span></div>' +
      '<div class="chart" role="img" aria-label="Run times: ' + esc(d.runtimes.map(function (r) { return r.date + ' ' + r.label + (r.slow ? ' (slow)' : ''); }).join(', ')) + '">' +
      (d.median_minutes ? '<div class="median" aria-hidden="true" style="bottom:' + Math.round(d.median_minutes * scale) + 'px"></div>' : '') +
      d.runtimes.map(function (r) {
        return '<div class="col"><b>' + esc(r.label) + '</b><div class="barv' + (r.slow ? ' slow' : '') + '" style="height:' + Math.round(r.minutes * scale) + 'px"></div></div>';
      }).join('') + '</div><div class="chart-dates">' + d.runtimes.map(function (r) { return '<span>' + esc(r.date) + '</span>'; }).join('') + '</div></section>';

    h += '<section class="card" aria-labelledby="pf-title"><h2 id="pf-title">Failing builds, by platform</h2>';
    if (!d.failing_builds.length) h += '<p class="empty">Nothing failing in the last run.</p>';
    d.failing_builds.forEach(function (f) {
      h += '<article class="fb"><div class="fb-head">' +
        (f.is_new ? '<span class="badge-new">NEW</span>' : knownBadge(f)) +
        '<b>' + esc(f.title) + '</b><span class="muted" style="font-size:13px">' + esc(f.job) + ' · failing since ' + esc(f.since) + '</span>' +
        link(f.build_url, 'Jenkins ' + esc(f.build) + ' →', 'details-link push') + '</div>';
      if (f.failed_platforms.length) {
        h += '<div class="plat-list">' + f.failed_platforms.map(function (p) {
          return '<span class="plat bad">' + esc(p) + ' ✕</span>';
        }).join('') + '</div>';
      }
      h += '<span class="muted" style="font-size:13px">' + esc(f.platform_note) + '</span>';
      h += '</article>';
    });
    return h + '</section>';
  }

  function render() {
    if (!data) return;
    if (!data.generated_at && !data.error) {
      app.innerHTML = '<p class="empty">Collecting QA data… The first start reads the latest QA runs from GitHub ' +
        'and can take several minutes; this page updates by itself.</p>';
      return;
    }
    var m = /^#pg(\d+)$/.exec(location.hash);
    app.innerHTML = m ? detail(m[1]) : overview();
    document.title = m ? 'PG ' + m[1] + ' · PPG Nightly QA' : 'PPG Nightly QA';
  }

  app.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-filter]');
    if (b) {
      filter = b.getAttribute('data-filter');
      render();
      var again = app.querySelector('button[data-filter="' + filter + '"]');
      if (again) again.focus();
    }
  });
  window.addEventListener('hashchange', function () { render(); window.scrollTo(0, 0); });

  function load() {
    fetch('data.json', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      data = d; render();
    }).catch(function (err) {
      if (!data) app.innerHTML = '<div class="alert" role="alert">Could not load the QA data: ' + esc(err.message) + '</div>';
    });
  }
  load();
  setInterval(load, 60000);
  setInterval(render, 30000); // keep "updated N min ago" current
})();
