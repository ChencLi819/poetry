/* ==========================================================================
   诗笺 · 前端应用
   页面结构对齐 poetry-app-prototype.html：首页 / 分类 / 详情 / 搜索 / 字典 / 我的
   数据全部来自原生 SQLite 语料库（351,653 篇），经 Android JavascriptInterface 桥接。
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------------------------------------------------------- 工具 */

  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /** 正文按行切块，空行不渲染。 */
  function lines(s) {
    return String(s || '').split('\n').map(function (x) { return x.trim(); })
      .filter(function (x) { return x.length; });
  }

  var WEEK = ['日', '一', '二', '三', '四', '五', '六'];

  function todayText() {
    var d = new Date();
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 · 星期' + WEEK[d.getDay()];
  }

  /** py 字段形如 "20:yú 21:zān"，下标是 UTF-16 码元序号，与 JS 字符串下标一致。 */
  function pyMap(py) {
    var map = {};
    String(py || '').split(/\s+/).forEach(function (pair) {
      var i = pair.indexOf(':');
      if (i > 0) map[pair.slice(0, i)] = pair.slice(i + 1);
    });
    return map;
  }

  var TONE_CHARS = {
    'āēīōūǖ': '阴平', 'áéíóúǘ': '阳平', 'ǎěǐǒǔǚ': '上声', 'àèìòùǜ': '去声'
  };
  function toneName(py) {
    for (var k in TONE_CHARS) {
      for (var i = 0; i < k.length; i++) {
        if (String(py).indexOf(k[i]) >= 0) return TONE_CHARS[k];
      }
    }
    return '轻声';
  }

  var CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩'];

  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.classList.add('on');
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.classList.remove('on'); }, 1800);
  }

  /* ------------------------------------------------------------ 数据桥接 */

  var Bridge = {
    seq: 0,
    pending: {},
    call: function (method, params) {
      var self = this;
      return new Promise(function (resolve, reject) {
        if (typeof Android === 'undefined') { resolve(Mock.call(method, params)); return; }
        var id = ++self.seq;
        self.pending[id] = { resolve: resolve, reject: reject };
        try {
          Android.request(JSON.stringify({ cb: id, m: method, p: params || {} }));
        } catch (e) {
          delete self.pending[id];
          reject(e);
        }
        setTimeout(function () {
          if (self.pending[id]) { delete self.pending[id]; reject(new Error('timeout')); }
        }, 20000);
      });
    }
  };

  /** 原生回调：payload 是 UTF-8 JSON 的 Base64，避开一切转义与 U+2028 坑。 */
  window.__bridgeRecv = function (id, b64) {
    var job = Bridge.pending[id];
    if (!job) return;
    delete Bridge.pending[id];
    var obj;
    try {
      obj = JSON.parse(decodeURIComponent(escape(atob(b64))));
    } catch (e) {
      job.reject(e); return;
    }
    if (obj && obj.error) job.reject(new Error(obj.error));
    else job.resolve(obj && obj.data !== undefined ? obj.data : obj);
  };

  /* ---------------------------------------------------------- 浏览器预览 */
  /* 未挂到 WebView 时用一份静态语料渲染，方便在桌面浏览器里核对版式。 */

  var MOCK_POEM = {
    id: 'mock1', ti: '水调歌头·明月几时有', au: '苏轼', dy: '宋代',
    pv: '但愿人长久，千里共婵娟。', tg: ['宋词', '中秋', '思念'],
    tx: '明月几时有？把酒问青天。\n不知天上宫阙，今夕是何年。\n我欲乘风归去，又恐琼楼玉宇，高处不胜寒。\n起舞弄清影，何似在人间。\n转朱阁，低绮户，照无眠。\n不应有恨，何事长向别时圆？\n人有悲欢离合，月有阴晴圆缺，此事古难全。\n但愿人长久，千里共婵娟。',
    py: '9:qióng 22:qǐ', yw: '明月从什么时候才开始出现的？我端起酒杯遥问苍天。\n不知道在天上的宫殿，今天晚上是何年何月。',
    zs: '把酒：端起酒杯。\n宫阙：宫殿。', bj: '这首词是公元1076年中秋，苏轼在密州所作。',
    jx: '全词意境豪放而阔大，情怀乐观而旷达。', sx: '', src: '宋词'
  };
  var MOCK_ZI = {
    zi: '婵', py: 'chán', tr: '嬋', radi: '女', stroke: 11,
    senses: '1. 见"婉婵"。\n2. 「婵娟」姿态美好。\n3. 指月亮。',
    gloss: '婵 (形声。从女,单声。本义婵娟形容女子姿态美好)',
    form: '', evidence: '但愿人长久,千里共婵娟。——苏轼《水调歌头》', phrase: '【婵娟】　【婵媛】'
  };

  var Mock = {
    call: function (m, p) {
      var base = [MOCK_POEM, {
        id: 'mock2', ti: '关山月', au: '徐陵', dy: '南北朝',
        pv: '关山三五月，客子忆秦川。', tg: ['边塞', '思念'], py: '', src: '古诗三百首',
        tx: '关山三五月，客子忆秦川。\n思妇高楼上，当窗应未眠。\n星旗映疏勒，云阵上祁连。\n战气今如此，从军复几年。'
      }, {
        id: 'mock3', ti: '静夜思', au: '李白', dy: '唐代',
        pv: '床前明月光，疑是地上霜。', tg: ['思乡'], py: '', src: '唐诗三百首',
        tx: '床前明月光，疑是地上霜。\n举头望明月，低头思故乡。'
      }, {
        // 长诗，用来验证列表里的折叠 / 展开
        id: 'mock4', ti: '琵琶行（节选）', au: '白居易', dy: '唐代',
        pv: '浔阳江头夜送客，枫叶荻花秋瑟瑟。', tg: ['七言古诗', '音乐'], py: '',
        src: '唐诗三百首',
        tx: '浔阳江头夜送客，枫叶荻花秋瑟瑟。\n主人下马客在船，举酒欲饮无管弦。\n' +
            '醉不成欢惨将别，别时茫茫江浸月。\n忽闻水上琵琶声，主人忘归客不发。\n' +
            '寻声暗问弹者谁，琵琶声停欲语迟。\n移船相近邀相见，添酒回灯重开宴。\n' +
            '千呼万唤始出来，犹抱琵琶半遮面。\n转轴拨弦三两声，未成曲调先有情。\n' +
            '弦弦掩抑声声思，似诉平生不得志。\n低眉信手续续弹，说尽心中无限事。\n' +
            '轻拢慢捻抹复挑，初为霓裳后六幺。\n大弦嘈嘈如急雨，小弦切切如私语。\n' +
            '嘈嘈切切错杂弹，大珠小珠落玉盘。\n间关莺语花底滑，幽咽泉流冰下难。\n' +
            '冰泉冷涩弦凝绝，凝绝不通声暂歇。'
      }];
      // 造 25 条，好让 20 条一页的续拉真的能翻出第二页
      var many = base.slice();
      while (many.length < 25) {
        base.forEach(function (b, i) {
          if (many.length < 25) many.push(Object.assign({}, b, { id: b.id + '_' + many.length }));
        });
      }
      function pg(list, offset, limit) {
        var o = offset || 0, n = limit || 20;
        return { total: list.length, offset: o, items: list.slice(o, o + n) };
      }
      switch (m) {
        case 'boot': return { count: 351653, authors: 14278 };
        case 'home': return {
          daily: MOCK_POEM, picks: many.slice(0, 4),
          cats: [{ zi: '唐诗', name: '全唐诗', n: 54514 }, { zi: '宋词', name: '宋词', n: 19846 },
                 { zi: '诗经', name: '诗经', n: 107 }, { zi: '古文', name: '古文观止', n: 183 }]
        };
        case 'facets': return {
          dynasties: [{ name: '宋代', n: 276206 }, { name: '唐代', n: 58865 },
                      { name: '元代', n: 11344 }, { name: '清代', n: 1179 },
                      { name: '先秦', n: 943 }, { name: '明代', n: 723 },
                      { name: '两汉', n: 444 }, { name: '南北朝', n: 437 }],
          collections: [{ name: '全宋诗', n: 252158 }, { name: '全唐诗', n: 54514 },
                        { name: '宋词', n: 19846 }, { name: '元曲', n: 8795 },
                        { name: '婉约词', n: 366 }, { name: '唐诗三百首', n: 236 },
                        { name: '古诗三百首', n: 196 }, { name: '乐府', n: 184 },
                        { name: '古文观止', n: 183 }, { name: '宋词精选', n: 114 }],
          tags: [{ name: '抒情', n: 2219 }, { name: '写景', n: 2138 }, { name: '写人', n: 1307 }]
        };
        case 'browse': return pg(many, p && p.offset);
        case 'poem': return Object.assign({}, MOCK_POEM, { fav: false });
        case 'search': return pg(many, p && p.offset);
        case 'hot': return {
          words: ['明月', '思乡', '边塞', '春晓', '李白', '中秋', '送别', '登高'],
          rank: many.slice(0, 8).map(function (x) {
            return { id: x.id, ti: x.ti, au: x.au, dy: x.dy, pv: x.pv };
          })
        };
        case 'zi': return p && p.c ? MOCK_ZI : null;
        case 'ziRecent': return ['婵', '疏', '月'];
        case 'stats': return { read: 86, fav: 12, zi: 37, week: [2, 3, 1, 4, 3, 5, 4], streak: 12 };
        case 'favList': return pg(many.slice(0, 12), p && p.offset);
        case 'picks': return many.slice(0, 4);
        default: return null;
      }
    }
  };

  /* ---------------------------------------------------------------- 路由 */

  var state = { tab: 'home', stack: [] };
  var view = { ruby: false, fsStep: 0, detailTab: 0 };
  var FS_STEPS = [1, 1.15, 1.32];

  var TABS = { home: 'scr-home', browse: 'scr-browse', search: 'scr-search', zi: 'scr-zi', me: 'scr-me' };
  var PUSH = { detail: 'scr-detail', list: 'scr-list', favlist: 'scr-list', zi: 'scr-zi' };
  var cache = {};

  function show(tab) {
    state.tab = tab;
    state.stack = [];
    render();
  }

  function push(name, params) {
    state.stack.push({ name: name, params: params });
    render();
  }

  function pop() {
    state.stack.pop();
    render();
  }

  /** 同步当前「可否返回」给原生，供物理返回键使用。 */
  function syncBack() {
    if (typeof Android !== 'undefined' && Android.onRoute) {
      try { Android.onRoute(state.stack.length, state.tab); } catch (e) { /* ignore */ }
    }
  }

  function render() {
    var top = state.stack[state.stack.length - 1];
    var name = top ? top.name : state.tab;
    var host = top ? PUSH[name] : TABS[state.tab];
    if (!host) host = TABS.home;

    // 注意取的是 TABS 的值（屏容器 id），不是键（tab 名）
    var screens = ['scr-home', 'scr-browse', 'scr-search', 'scr-zi', 'scr-me',
                   'scr-detail', 'scr-list'];
    screens.forEach(function (id) {
      var el = $(id);
      if (el) el.classList.toggle('on', id === host);
    });

    document.querySelectorAll('#nav .nav-item').forEach(function (el) {
      el.classList.toggle('on', !top && el.getAttribute('data-tab') === state.tab);
    });

    syncBack();
    setPager(null);        // 换屏先摘掉上一屏的续拉钩子，各屏渲染时自己再挂
    var params = top ? top.params : {};
    if (name === 'home') renderHome();
    else if (name === 'browse') renderBrowse();
    else if (name === 'search') renderSearch();
    else if (name === 'me') renderMe();
    else if (name === 'zi') renderZi(params.c);
    else if (name === 'detail') renderDetail(params.id);
    else if (name === 'list') renderList(params);
    else if (name === 'favlist') renderFavList();
  }

  /* ------------------------------------------------------------ 片段渲染 */

  /** 列表里直接铺全文；没有正文的（比如公开语料缺字段）退回 preview。 */
  function poemLines(p) {
    var t = String(p.tx || '').split('\n').map(function (x) { return x.trim(); })
      .filter(function (x) { return x.length; });
    if (!t.length && p.pv) t = [p.pv];
    return t;
  }

  var CLAMP_LINES = 10;   // 超过这么多行先折叠，避免长诗把列表撑爆

  function feedItem(p) {
    var ls = poemLines(p);
    var long = ls.length > CLAMP_LINES;
    var tags = (p.tg || []).slice(0, 3).map(function (t) {
      return '<span class="tag">' + esc(t) + '</span>';
    }).join('');
    return '<div class="feed-item" data-act="poem" data-id="' + esc(p.id) + '">' +
      '<div class="verse-prev">' +
      '<h4>' + esc(p.ti) + '</h4>' +
      '<p class="by">' + esc([p.dy, p.au, p.src].filter(Boolean).join(' · ')) + '</p>' +
      '<div class="full' + (long ? ' clamp' : '') + '">' +
      ls.map(function (l) { return '<i>' + esc(l) + '</i>'; }).join('') +
      '</div>' +
      (long ? '<span class="more-lines" data-act="expand">展开全文 · 共 ' +
        ls.length + ' 行 &rsaquo;</span>' : '') +
      (tags ? '<div class="tags">' + tags + '</div>' : '') +
      '</div>' +
      '<div class="like' + (p.fav ? ' on' : '') + '" data-act="fav" data-id="' + esc(p.id) + '">' +
      (p.fav ? '&#9829;' : '&#9825;') + '</div></div>';
  }

  /* ---------- 分页列表的公共骨架：rows 装条目，tail 装「加载中 / 到底了」 ---------- */

  function listShell(id, n) {
    return '<div class="rows" id="' + id + '-rows">' + skeleton(n || 3) + '</div>' +
           '<div class="tail" id="' + id + '-tail"></div>';
  }

  /** reset=true 整段重画；否则只往 rows 尾部追加，滚动位置不会跳。 */
  function paintRows(id, items, reset) {
    var r = $(id + '-rows');
    if (!r) return;
    if (!items.length && reset) {
      r.innerHTML = '<div class="empty">没有找到相关诗文</div>';
      return;
    }
    var frag = document.createElement('div');
    frag.innerHTML = items.map(feedItem).join('');
    if (reset) {
      r.innerHTML = '';
    }
    while (frag.firstChild) r.appendChild(frag.firstChild);
  }

  function paintTail(id, state) {
    var t = $(id + '-tail');
    if (!t) return;
    t.innerHTML = state === 'loading'
      ? '<div class="tail-load"><i></i><i></i><i></i>正在载入…</div>'
      : state === 'end' ? '<div class="tail-end">— 已到末尾 —</div>' : '';
  }

  /** 底部滚动到底自动续拉；每个列表屏渲染时登记自己的 loader。 */
  var pager = { fn: null };

  function setPager(fn) { pager.fn = fn || null; }

  function bindPagers() {
    ['scr-home', 'scr-browse', 'scr-search', 'scr-zi', 'scr-me', 'scr-detail', 'scr-list']
      .forEach(function (id) {
        var el = $(id);
        if (!el || el._pgBound) return;
        el._pgBound = true;
        el.addEventListener('scroll', function () {
          if (!this.classList.contains('on') || !pager.fn) return;
          if (this.scrollTop + this.clientHeight >= this.scrollHeight - 280) {
            var f = pager.fn;
            pager.fn = null;      // 先摘掉，回调里再挂回，避免一次滚动连发
            f();
          }
        });
      });
  }

  function skeleton(n) {
    var s = '';
    for (var i = 0; i < n; i++) s += '<div class="skeleton"></div>';
    return s;
  }

  /** 逐字包一层可点的 span；下标必须与 Java 侧一致，换行符也要计数。 */
  function verseHtml(text, py) {
    var map = pyMap(py);
    var idx = 0;
    return String(text || '').split('\n').map(function (line) {
      var out = '';
      for (var i = 0; i < line.length; i++) {
        var ch = line[i];
        var r = map[idx];
        out += '<span class="rb c" data-act="zi" data-c="' + esc(ch) + '"' +
          (r ? ' data-py="' + esc(r) + '"' : '') + '>' + esc(ch) + '</span>';
        idx++;
      }
      idx++;   // 换行符本身也占一个码元
      return out ? '<i>' + out + '</i>' : '';
    }).join('');
  }

  /* ------------------------------------------------------------ 屏 1 首页 */

  function renderHome() {
    var host = $('scr-home');
    if (cache.home) { host.innerHTML = cache.home; return; }
    host.innerHTML =
      '<div class="home-greet"><div class="date">' + todayText() + '</div>' +
      '<h2>今日宜读<em>诗</em></h2></div>' +
      '<div id="hero-slot">' + skeleton(1) + '</div>' +
      '<div class="section-h"><b>分类浏览</b><a data-act="tab" data-tab="browse">全部 &rsaquo;</a></div>' +
      '<div id="cat-slot"><div class="cat-grid">' + skeleton(0) + '</div></div>' +
      '<div class="section-h"><b>为你推荐</b><a data-act="repick">换一批</a></div>' +
      '<div id="pick-slot">' + skeleton(3) + '</div>';

    Bridge.call('home', {}).then(function (d) {
      if (!d) { $('hero-slot').innerHTML = '<div class="empty">没有读到诗文数据</div>'; return; }
      paintHome(d);
      cache.home = host.innerHTML;
    }).catch(function (e) {
      $('hero-slot').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  function paintHome(d) {
    var p = d.daily || {};
    var v = lines(p.tx || p.pv || '').slice(0, 2).map(function (l) {
      return '<i>' + esc(l) + '</i>';
    }).join('');
    $('hero-slot').innerHTML =
      '<div class="hero-card" data-act="poem" data-id="' + esc(p.id) + '">' +
      '<div class="hero-moon"></div>' +
      '<span class="badge">每日一诗</span>' +
      '<h3>' + esc(p.ti) + '</h3>' +
      '<div class="who">' + esc([p.au, p.dy, p.src].filter(Boolean).join(' · ')) + '</div>' +
      '<div class="verse">' + v + '</div>' +
      '<div class="ops">' +
      '<div class="op pri" data-act="speak" data-id="' + esc(p.id) + '">开始诵读</div>' +
      '<div class="op" data-act="fav" data-id="' + esc(p.id) + '">加入收藏</div>' +
      '</div></div>';

    $('cat-slot').innerHTML = '<div class="cat-grid">' + (d.cats || []).map(function (c) {
      return '<div class="cat-cell" data-act="list" data-kind="src" data-name="' + esc(c.name) + '">' +
        '<div class="zi"><b>' + esc(c.zi.slice(0, 1)) + '</b><span>' + esc(c.zi.slice(1)) + '</span></div>' +
        '<small>' + esc(c.name) + ' ' + c.n + ' 首</small></div>';
    }).join('') + '</div>';

    paintPicks(d.picks || []);
  }

  function paintPicks(list) {
    $('pick-slot').innerHTML = list.map(feedItem).join('') ||
      '<div class="empty">暂时没有推荐</div>';
  }

  /* ------------------------------------------------------------ 屏 2 分类 */

  var browse = { dy: '', src: '', tag: '', offset: 0, total: 0, items: [], busy: false };

  function renderBrowse() {
    var host = $('scr-browse');
    host.innerHTML =
      '<div class="topbar"><span class="t-title">分类</span><span class="t-act" id="b-total">共 35 万首</span></div>' +
      '<div id="dy-slot"></div><div id="src-slot"></div>' +
      '<div id="card-slot"></div><div class="list-wrap">' + listShell('b', 4) + '</div>';
    if (cache.facets) { paintBrowseShell(cache.facets); loadBrowse(true); return; }
    Bridge.call('facets', {}).then(function (f) {
      cache.facets = f;
      paintBrowseShell(f);
      loadBrowse(true);
    }).catch(function (e) {
      $('list-slot').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  function paintBrowseShell(f) {
    var dys = [{ name: '', n: 0 }].concat(f.dynasties || []);
    $('dy-slot').innerHTML = '<div class="dyn-tabs">' + dys.map(function (d) {
      return '<span class="chip' + (browse.dy === d.name ? ' on' : '') + '" data-act="dy" data-name="' +
        esc(d.name) + '">' + esc(d.name || '全部') + '</span>';
    }).join('') + '</div>';

    var srcs = f.collections || [];
    $('src-slot').innerHTML = '<div class="filter-bar">' + srcs.map(function (s) {
      return '<span class="chip' + (browse.src === s.name ? ' on' : '') + '" data-act="src" data-name="' +
        esc(s.name) + '">' + esc(s.name) + '</span>';
    }).join('') + '</div>';

    paintBrowseCard();
  }

  function paintBrowseCard() {
    var title = browse.src || browse.dy || '全部藏书';
    var sub = browse.src ? (browse.dy ? browse.dy + ' · ' : '') + '收录 ' + browse.total + ' 首'
      : browse.dy ? '收录 ' + browse.total + ' 首' : '按朝代与诗集翻检全部藏书';
    $('card-slot').innerHTML =
      '<div class="cat-card" data-act="noop">' +
      '<div><h4>' + esc(title) + '</h4><small>' + esc(sub) + '</small></div>' +
      '<span class="arrow">&rsaquo;</span><span class="big">' + esc(title.slice(0, 1)) + '</span></div>';
  }

  function loadBrowse(reset) {
    if (browse.busy) return;
    if (reset) { browse.offset = 0; browse.items = []; }
    if (reset) paintRows('b', [], true);
    paintTail('b', 'loading');
    browse.busy = true;
    Bridge.call('browse', {
      dy: browse.dy, src: browse.src, tag: browse.tag, offset: browse.offset
    }).then(function (r) {
      browse.total = r.total || 0;
      browse.items = browse.items.concat(r.items || []);
      browse.offset = browse.items.length;
      browse.busy = false;
      renderBrowseRows();
      paintBrowseCard();
      var t = $('b-total');
      if (t) t.textContent = '共 ' + browse.total + ' 首';
    }).catch(function (e) {
      browse.busy = false;
      paintRows('b', [], true);
      paintTail('b', 'none');
      var r = $('b-rows');
      if (r) r.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  /** 换筛选条件时整段重画并回到顶部；还有余量就把续拉的钩子挂回去。 */
  function renderBrowseRows() {
    paintRows('b', browse.items, true);
    var more = browse.items.length < browse.total;
    paintTail('b', more ? 'loading' : (browse.items.length ? 'end' : 'none'));
    $('scr-browse').scrollTop = 0;
    setPager(more ? browseNext : null);
  }

  function browseNext() {
    if (browse.busy) { setPager(browseNext); return; }
    paintTail('b', 'loading');
    Bridge.call('browse', {
      dy: browse.dy, src: browse.src, tag: browse.tag, offset: browse.offset
    }).then(function (r) {
      var fresh = r.items || [];
      browse.items = browse.items.concat(fresh);
      browse.offset = browse.items.length;
      paintRows('b', fresh, false);
      var more = browse.items.length < browse.total;
      paintTail('b', more ? 'loading' : 'end');
      if (more) setPager(browseNext);
      paintBrowseCard();
    }).catch(function () {
      paintTail('b', 'end');
    });
  }

  /* ------------------------------------------------------------ 列表页 */

  var pageState = { kind: 'src', name: '', items: [], total: 0, offset: 0, busy: false };

  function renderList(params) {
    pageState.kind = params.kind || 'src';
    pageState.name = params.name;
    pageState.items = [];
    pageState.total = 0;
    pageState.offset = 0;
    pageState.busy = false;
    $('scr-list').innerHTML =
      '<div class="topbar"><span class="t-back" data-act="back">&lsaquo;</span>' +
      '<span class="t-title">' + esc(params.name) + '</span>' +
      '<span class="t-act" id="p-total"></span></div>' +
      '<div class="list-wrap">' + listShell('p', 4) + '</div>';
    pageNext();
  }

  function pageNext() {
    if (pageState.busy) { setPager(pageNext); return; }
    pageState.busy = true;
    paintTail('p', 'loading');
    Bridge.call('browse', {
      dy: '', src: pageState.kind === 'src' ? pageState.name : '',
      tag: pageState.kind === 'tag' ? pageState.name : '', offset: pageState.offset
    }).then(function (r) {
      pageState.busy = false;
      var fresh = r.items || [];
      pageState.total = r.total || 0;
      pageState.items = pageState.items.concat(fresh);
      pageState.offset = pageState.items.length;
      paintRows('p', fresh, pageState.offset === fresh.length);
      var more = pageState.items.length < pageState.total;
      paintTail('p', more ? 'loading' : (pageState.items.length ? 'end' : 'none'));
      var t = $('p-total');
      if (t) t.textContent = pageState.total + ' 首';
      if (more) setPager(pageNext);
    }).catch(function (e) {
      pageState.busy = false;
      paintTail('p', 'none');
      var r = $('p-rows');
      if (r) r.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  /* ------------------------------------------------------------ 屏 3 详情 */

  var detail = null;

  function renderDetail(id) {
    var host = $('scr-detail');
    // 每次都先把骨架写进去：从别的屏切回来时容器里的旧节点不一定还在
    host.innerHTML =
      '<div class="topbar"><span class="t-back" data-act="back">&lsaquo;</span>' +
      '<span class="t-title">诗 · 文</span><span class="t-act">&ctdot;</span></div>' +
      '<div id="d-body">' + skeleton(3) + '</div>';
    if (detail && detail.id === id) { paintDetail(); return; }
    Bridge.call('poem', { id: id }).then(function (p) {
      if (!p) { host.innerHTML = '<div class="empty">这篇没有找到</div>'; return; }
      detail = p;
      view.detailTab = 0;
      paintDetail();
      if (typeof Android !== 'undefined' && Android.markRead) {
        try { Android.markRead(id); } catch (e) { /* ignore */ }
      }
    }).catch(function (e) {
      host.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  function detailSections(p) {
    var out = [];
    if (p.yw) out.push({ k: '译文', v: p.yw });
    if (p.zs) out.push({ k: '注释', v: p.zs });
    if (p.jx || p.sx) out.push({ k: '赏析', v: p.jx || p.sx });
    if (p.bj) out.push({ k: '背景', v: p.bj });
    if (p.src) out.push({ k: '出处', v: p.src });
    return out;
  }

  /**
   * 整篇只在打开时画一次。
   * 之后切标签、开关注音、调字号都只改对应的那一小块 DOM，
   * 不动标签条、不重建正文，页面也就不会跳回顶部。
   */
  function paintDetail() {
    var p = detail;
    if (!p) return;
    var secs = detailSections(p);
    if (view.detailTab >= secs.length) view.detailTab = 0;

    var rare = [];
    var map = pyMap(p.py);
    Object.keys(map).forEach(function (i) {
      var ch = (p.tx || '')[i];
      if (ch) rare.push({ c: ch, py: map[i] });
    });
    var tip = rare.length
      ? '<div class="dict-tip" data-act="zi" data-c="' + esc(rare[0].c) + '">' +
        '<div class="zi-box">' + esc(rare[0].c) + '</div>' +
        '<div class="tx"><b>文中生字 · 「' + esc(rare[0].c) + '」</b><br>拼音 ' +
        esc(rare[0].py) + '，点击查看释义</div>' +
        '<div class="go">&rsaquo;</div></div>'
      : '';

    $('d-body').innerHTML =
      '<div class="poem-body">' +
      '<h3>' + esc(p.ti) + '</h3>' +
      '<div class="meta">' + esc([p.dy, p.au, p.src].filter(Boolean).join(' · ')) + '</div>' +
      '<div class="verse' + (view.ruby ? ' ruby-on' : '') + '" id="verse">' +
      verseHtml(p.tx || p.pv || '', p.py) + '</div>' +
      ((p.tg || []).length
        ? '<div class="poem-tags">' + p.tg.map(function (t) {
            return '<span class="tag" data-act="list" data-kind="tag" data-name="' + esc(t) + '">' + esc(t) + '</span>';
          }).join('') + '</div>' : '') +
      '</div>' +

      '<div class="act-bar">' +
      '<div class="a' + (p.fav ? ' hot' : '') + '" id="act-fav" data-act="fav" data-id="' + esc(p.id) + '">' +
      '<svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.8-9.5-9C1 8.5 3 5 6.5 5c2.2 0 3.9 1.3 5.5 3.4C13.6 6.3 15.3 5 17.5 5 21 5 23 8.5 21.5 12c-2 4.2-9.5 9-9.5 9z"/></svg>' +
      '<span class="lbl">' + (p.fav ? '已收藏' : '收藏') + '</span></div>' +
      '<div class="a" data-act="speak" data-id="' + esc(p.id) + '">' +
      '<svg viewBox="0 0 24 24"><path d="M4 10v4h3l5 4V6l-5 4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/></svg>诵读</div>' +
      '<div class="a" data-act="toyiwen">' +
      '<svg viewBox="0 0 24 24"><rect x="5" y="4" width="14" height="16" rx="2"/><path d="M9 9h6M9 13h6M9 17h4"/></svg>译文</div>' +
      '<div class="a' + (view.ruby ? ' on' : '') + '" id="act-ruby" data-act="ruby">' +
      '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 8v4l3 2"/></svg>注音</div>' +
      '<div class="a" data-act="fs">' +
      '<svg viewBox="0 0 24 24"><path d="M4 18 9 6l5 12"/><path d="M6 14h6"/><path d="M15 18l4-8 4 8"/><path d="M16.5 15h5"/></svg>字号</div>' +
      '</div>' +

      '<div class="tab-sticky">' +
      (secs.length ? '<div class="detail-tabs" id="d-tabs">' + secs.map(function (s, i) {
        return '<span class="' + (i === view.detailTab ? 'on' : '') + '" data-act="dtab" data-i="' + i + '">' +
          esc(s.k) + '</span>';
      }).join('') + '</div>' : '') +
      '<div id="d-panel">' + panelHtml(secs) + '</div>' +
      '</div>' +

      tip;
  }

  /** 只有标签内容区重画；标签条本身和上面的正文都留在原地。 */
  function panelHtml(secs) {
    var cur = secs[view.detailTab];
    if (!cur) {
      return '<div class="yiwen-box"><b>说明</b><span class="ln">这篇只有正文，暂无注释与译文。可点正文里的字查字典。</span></div>';
    }
    return '<div class="yiwen-box" id="yw-box"><b>' + esc(cur.k) + '</b>' +
      lines(cur.v).map(function (l) { return '<span class="ln">' + esc(l) + '</span>'; }).join('') +
      '</div>';
  }

  function repaintPanel() {
    var box = $('d-panel');
    if (box && detail) box.innerHTML = panelHtml(detailSections(detail));
  }

  function syncTabs() {
    var tabs = $('d-tabs');
    if (!tabs) return;
    tabs.querySelectorAll('span[data-act="dtab"]').forEach(function (s) {
      s.classList.toggle('on', parseInt(s.getAttribute('data-i'), 10) === view.detailTab);
    });
  }

  /* ------------------------------------------------------------ 屏 4 搜索 */

  var searchState = { q: '', hot: null, results: null, items: [], total: 0, offset: 0, busy: false };

  function renderSearch() {
    var host = $('scr-search');
    var keep = $('q') ? $('q').value : '';
    // 每次重建外壳（输入框也一并重建），否则从别的屏切回来会拿到空容器
    host.innerHTML =
      '<div class="topbar"><span class="t-title">搜索</span>' +
      '<span class="t-act" data-act="clearsearch">清空</span></div>' +
      '<div class="search-box">' +
      '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>' +
      '<input id="q" placeholder="搜索诗名、诗句、作者…" autocomplete="off">' +
      '<span class="btn" data-act="dosearch">搜索</span></div>' +
      '<div id="s-body">' + skeleton(4) + '</div>';
    if (keep) $('q').value = keep;

    if (searchState.results) { paintSearch(); return; }
    if (searchState.hot) { paintSearch(); return; }
    Bridge.call('hot', {}).then(function (d) {
      searchState.hot = d;
      paintSearch();
    }).catch(function () { paintSearch(); });
  }

  function paintSearch() {
    var body = $('s-body');
    if (!body) return;
    if (searchState.results) {
      body.innerHTML =
        '<div class="section-h"><b>检索结果</b><a data-act="clearsearch">共 ' +
        searchState.total + ' 篇 · 返回热榜</a></div>' +
        '<div class="list-wrap">' + listShell('r', 3) + '</div>';
      renderSearchRows();
      return;
    }
    var d = searchState.hot || { words: [], rank: [] };
    body.innerHTML =
      '<div class="section-h"><b>热门搜索</b></div>' +
      '<div class="hot-cloud">' + (d.words || []).map(function (w) {
        return '<span class="chip big" data-act="q" data-q="' + esc(w) + '">' + esc(w) + '</span>';
      }).join('') + '</div>' +
      '<div class="section-h"><b>诗词热榜</b><a>今日 · 实时</a></div>' +
      (d.rank || []).map(function (r, i) {
        return '<div class="rank-item" data-act="poem" data-id="' + esc(r.id) + '">' +
          '<span class="no">' + (i + 1) + '</span>' +
          '<div class="rt"><b>' + esc(r.ti) + '</b><small>' +
          esc([r.au, r.dy, r.pv].filter(Boolean).join(' · ')) + '</small></div>' +
          '<span class="trend">' + esc(r.dy || '') + '</span></div>';
      }).join('');
  }

  /** 一次检索的结果整段重画，续拉只往尾部追加，滚动位置不动。 */
  function renderSearchRows() {
    paintRows('r', searchState.items, true);
    var more = searchState.items.length < searchState.total;
    paintTail('r', more ? 'loading' : (searchState.items.length ? 'end' : 'none'));
    if (more) setPager(searchNext);
  }

  function doSearch() {
    var el = $('q');
    var q = (el && el.value || '').trim();
    if (!q) { toast('请输入关键词'); return; }
    searchState.q = q;
    searchState.results = [];
    searchState.items = [];
    searchState.total = 0;
    searchState.offset = 0;
    $('s-body').innerHTML =
      '<div class="section-h"><b>检索结果</b><a data-act="clearsearch">检索中…</a></div>' +
      '<div class="list-wrap">' + listShell('r', 4) + '</div>';
    searchNext();
  }

  function searchNext() {
    if (searchState.busy) { setPager(searchNext); return; }
    searchState.busy = true;
    paintTail('r', 'loading');
    Bridge.call('search', { q: searchState.q, offset: searchState.offset })
      .then(function (r) {
        searchState.busy = false;
        var fresh = r.items || [];
        searchState.total = r.total || 0;
        searchState.items = searchState.items.concat(fresh);
        searchState.offset = searchState.items.length;
        searchState.results = searchState.items;
        paintRows('r', fresh, searchState.offset === fresh.length);
        var more = searchState.items.length < searchState.total;
        paintTail('r', more ? 'loading' : (searchState.items.length ? 'end' : 'none'));
        var a = $('s-body').querySelector('.section-h a');
        if (a) a.textContent = '共 ' + searchState.total + ' 篇 · 返回热榜';
        if (more) setPager(searchNext);
      })
      .catch(function (e) {
        searchState.busy = false;
        paintTail('r', 'none');
        var box = $('r-rows');
        if (box) box.innerHTML = '<div class="empty">检索失败：' + esc(e.message) + '</div>';
      });
  }

  /* ------------------------------------------------------------ 屏 5 字典 */

  var ziState = { c: '', data: null, recent: [], recentFetched: false };

  function renderZi(c) {
    var host = $('scr-zi');
    if (!c) {
      if (!ziState.recentFetched) {
        ziState.recentFetched = true;
        Bridge.call('ziRecent', {}).then(function (r) {
          ziState.recent = r || [];
          var top = state.stack[state.stack.length - 1];
          if (!top && state.tab === 'zi') paintZiLand();
        }).catch(function () { /* 忽略：最近查字只是锦上添花 */ });
      }
      paintZiLand();
      return;
    }
    // 骨架先落盘，避免复用缓存时容器里已经没有 #z-body
    host.innerHTML =
      '<div class="topbar"><span class="t-back" data-act="back">&lsaquo;</span>' +
      '<span class="t-title">字 · 典</span><span class="t-act">1.4 万字</span></div>' +
      '<div id="z-body">' + skeleton(3) + '</div>';
    if (ziState.data && ziState.data.zi === c) { paintZi(); return; }
    Bridge.call('zi', { c: c }).then(function (d) {
      ziState.data = d;
      paintZi();
    }).catch(function () {
      $('z-body').innerHTML = '<div class="empty">查字失败</div>';
    });
  }

  var COMMON = '天地人日月星风雨雪山水花草木金石火土江海春夏秋冬';

  function paintZiLand() {
    var host = $('scr-zi');
    host.innerHTML =
      '<div class="topbar"><span class="t-title">字 · 典</span><span class="t-act">1.4 万字</span></div>' +
      '<div class="search-box">' +
      '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>' +
      '<input id="zc" placeholder="输入一个汉字，查音义…" autocomplete="off" maxlength="1">' +
      '<span class="btn" data-act="dozi">查字</span></div>' +
      (ziState.recent.length
        ? '<div class="zi-sec"><div class="h">最 近 查 过</div><div class="zi-grid">' +
          ziState.recent.map(function (c) {
            return '<div class="z" data-act="zi" data-c="' + esc(c) + '">' + esc(c) + '</div>';
          }).join('') + '</div></div>'
        : '') +
      '<div class="zi-sec"><div class="h">常 用 字</div><div class="zi-grid">' +
      COMMON.split('').map(function (c) {
        return '<div class="z" data-act="zi" data-c="' + esc(c) + '">' + esc(c) + '</div>';
      }).join('') + '</div></div>' +
      '<div class="zi-sec" style="margin-bottom:16px;"><div class="h">说 明</div>' +
      '<div class="quote-box">读诗遇到生字，可在诗文详情页直接点正文里的任意一个字，' +
      '这里会给出拼音、部首、笔画、释义与古诗词书证。<br>' +
      '<span class="src">字典：新华字典数据库 chinese-xinhua（MIT）</span></div></div>';
  }

  function paintZi() {
    var d = ziState.data;
    var body = $('z-body');
    if (!body) return;
    if (!d) {
      body.innerHTML = '<div class="empty">这部字典未收该字</div>';
      return;
    }
    var stats = ['部首 ' + d.radi, d.stroke + ' 画'];
    if (d.tr && d.tr !== d.zi) stats.push('繁体 ' + d.tr);
    // 声调已经在拼音旁边标过一次，别再当成一条属性重复一遍

    var senses = lines(d.senses).map(function (s, i) {
      return '<div class="sense-item"><b>' + (CIRCLED[i] || '·') + '</b><div>' +
        esc(s.replace(/^[⒈-⒛0-9]+[.、．]?\s*/, '')) + '</div></div>';
    }).join('');

    var ev = lines(d.evidence).map(function (l) {
      return '<div>' + esc(l) + '</div>';
    }).join('');

    var phrases = String(d.phrase || '').split(/[\s　]+/).filter(Boolean).map(function (p) {
      return '<span class="tag">' + esc(p.replace(/[【】]/g, '')) + '</span>';
    }).join(' ');

    body.innerHTML =
      '<div class="zi-hero"><div class="big-z">' + esc(d.zi) + '</div>' +
      '<div class="info"><div class="py">' + esc(d.py) +
      '<span>' + esc(toneName(d.py)) + '</span></div>' +
      '<div class="stats">' + stats.map(function (s) {
        return '<span>' + esc(s) + '</span>';
      }).join('') + '</div></div></div>' +

      (senses ? '<div class="zi-sec"><div class="h">基 本 释 义</div>' + senses + '</div>' : '') +

      '<div class="zi-sec"><div class="h">笔 顺 演 示</div>' +
      '<div class="stroke-demo">' +
      '<div class="cell g1"><i>' + esc(d.zi) + '</i></div>' +
      '<div class="cell g2"><i>' + esc(d.zi) + '</i></div>' +
      '<div class="cell g3"><i>' + esc(d.zi) + '</i></div>' +
      '<div class="cell"><i>' + esc(d.zi) + '</i></div>' +
      '<div><small>共 ' + d.stroke + ' 画</small></div></div></div>' +

      (ev ? '<div class="zi-sec"><div class="h">诗 句 用 例</div><div class="quote-box">' + ev + '</div></div>' : '') +
      (phrases ? '<div class="zi-sec"><div class="h">词 例</div><div>' + phrases + '</div></div>' : '') +
      (d.gloss ? '<div class="zi-sec" style="margin-bottom:16px;"><div class="h">古 义</div>' +
        '<div class="quote-box">' + esc(d.gloss) + '</div></div>' : '');
  }

  /* ------------------------------------------------------------ 屏 6 我的 */

  function renderMe() {
    var host = $('scr-me');
    host.innerHTML =
      '<div class="topbar"><span class="t-title">我 的</span><span class="t-act">&#9881;</span></div>' +
      '<div id="me-body">' + skeleton(4) + '</div>';
    Bridge.call('stats', {}).then(function (s) { paintMe(s || {}); })
      .catch(function (e) {
        $('me-body').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
      });
  }

  function paintMe(s) {
    var week = s.week || [0, 0, 0, 0, 0, 0, 0];
    var max = Math.max.apply(null, week.concat([1]));
    var order = [1, 2, 3, 4, 5, 6, 0];   // 周一 → 周日
    var todayIdx = new Date().getDay();

    $('me-body').innerHTML =
      '<div class="me-head"><div class="avatar">月</div>' +
      '<div class="n"><b>青莲居士</b><p>已坚持诵读 <em>' + (s.streak || 0) +
      '</em> 天 · 已读 <em>' + (s.read || 0) + '</em> 首</p></div></div>' +

      '<div class="stat-strip">' +
      '<div class="s"><b><em>' + (s.read || 0) + '</em></b><small>已读诗词</small></div>' +
      '<div class="s" data-act="favlist"><b>' + (s.fav || 0) + '</b><small>收藏</small></div>' +
      '<div class="s" data-act="zitab"><b>' + (s.zi || 0) + '</b><small>查过字</small></div>' +
      '</div>' +

      '<div class="week-card"><div class="h">本周诵读<span>' + todayText() + '</span></div>' +
      '<div class="bars">' + order.map(function (d) {
        var v = week[d] || 0;
        return '<div class="b' + (d === todayIdx ? ' on' : '') + '">' +
          '<i style="height:' + Math.round(v * 100 / max) + '%"></i><small>' + WEEK[d] + '</small></div>';
      }).join('') + '</div></div>' +

      '<div class="me-list">' +
      '<div class="me-row" data-act="favlist"><div class="ic a">&#9829;</div>我的收藏' +
      '<span class="cnt">' + (s.fav || 0) + ' 首</span><span class="arr">&rsaquo;</span></div>' +
      '<div class="me-row" data-act="zitab"><div class="ic b">&#9776;</div>查字记录' +
      '<span class="cnt">' + (s.zi || 0) + ' 字</span><span class="arr">&rsaquo;</span></div>' +
      '<div class="me-row" data-act="noop"><div class="ic c">&#8595;</div>离线诗库' +
      '<span class="cnt">随包 35 万首</span><span class="arr">&rsaquo;</span></div>' +
      '<div class="me-row" data-act="noop"><div class="ic b">&#9678;</div>学习目标' +
      '<span class="cnt">每日 2 首</span><span class="arr">&rsaquo;</span></div>' +
      '</div>' +

      '<div class="about">诗笺 · 水墨宣纸版<br>' +
      '正文：chinese-poetry 公开语料（MIT）　注释译文：公开网络资料，版权归原作者所有<br>' +
      '字典：新华字典数据库 chinese-xinhua（MIT）</div>';
  }

  /* ------------------------------------------------------------ 收藏列表 */

  var favState = { items: [], total: 0, offset: 0, busy: false };

  function renderFavList() {
    favState.items = [];
    favState.total = 0;
    favState.offset = 0;
    favState.busy = false;
    $('scr-list').innerHTML =
      '<div class="topbar"><span class="t-back" data-act="back">&lsaquo;</span>' +
      '<span class="t-title">我的收藏</span><span class="t-act" id="f-total"></span></div>' +
      '<div class="list-wrap">' + listShell('f', 3) + '</div>';
    favNext();
  }

  function favNext() {
    if (favState.busy) { setPager(favNext); return; }
    favState.busy = true;
    paintTail('f', 'loading');
    Bridge.call('favList', { offset: favState.offset }).then(function (r) {
      favState.busy = false;
      var fresh = r.items || [];
      favState.total = r.total || 0;
      favState.items = favState.items.concat(fresh);
      favState.offset = favState.items.length;
      paintRows('f', fresh, favState.offset === fresh.length);
      if (!favState.items.length) {
        var box = $('f-rows');
        if (box) box.innerHTML = '<div class="empty">还没有收藏。<br>读到喜欢的句子，点星标即可。</div>';
      }
      var more = favState.items.length < favState.total;
      paintTail('f', more ? 'loading' : (favState.items.length ? 'end' : 'none'));
      var t = $('f-total');
      if (t) t.textContent = favState.total + ' 首';
      if (more) setPager(favNext);
    }).catch(function () {
      favState.busy = false;
      paintTail('f', 'none');
    });
  }

  /* ------------------------------------------------------------ 事件委托 */

  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');

    // 收藏按钮在条目内部，先于条目跳转处理
    if (act === 'fav') {
      e.stopPropagation();
      var id = el.getAttribute('data-id');
      Bridge.call('favToggle', { id: id }).then(function (on) {
        toast(on ? '已加入收藏' : '已取消收藏');
        var mark = el.classList.contains('like') ? el : el;
        if (el.classList.contains('like')) {
          el.classList.toggle('on', !!on);
          el.innerHTML = on ? '&#9829;' : '&#9825;';
        } else if (detail && detail.id === id) {
          // 只换收藏按钮自己的样子，正文和标签页一概不重建
          detail.fav = !!on;
          var b = $('act-fav');
          if (b) {
            b.classList.toggle('hot', !!on);
            var lbl = b.querySelector('.lbl');
            if (lbl) lbl.textContent = on ? '已收藏' : '收藏';
          }
        }
        cache.home = null;
      }).catch(function () { toast('收藏失败'); });
      return;
    }

    switch (act) {
      case 'noop':
        break;
      case 'back':
        pop();
        break;
      case 'tab':
        show(el.getAttribute('data-tab'));
        break;
      case 'poem':
        push('detail', { id: el.getAttribute('data-id') });
        break;
      case 'list':
        push('list', {
          kind: el.getAttribute('data-kind') || 'src',
          name: el.getAttribute('data-name'),
          total: ''
        });
        break;
      case 'zi':
        push('zi', { c: el.getAttribute('data-c') });
        break;
      case 'zitab':
        show('zi');
        break;
      case 'favlist':
        push('favlist', {});
        break;
      case 'repick':
        $('pick-slot').innerHTML = skeleton(3);
        Bridge.call('picks', { seed: Date.now() % 100000 }).then(function (list) {
          paintPicks(list || []);
          cache.home = $('scr-home').innerHTML;
        }).catch(function () { toast('换一批失败'); });
        break;
      case 'dy':
        browse.dy = el.getAttribute('data-name');
        browse.src = '';
        browse.tag = '';
        paintBrowseShell(cache.facets);
        loadBrowse(true);
        break;
      case 'src':
        var n = el.getAttribute('data-name');
        browse.src = browse.src === n ? '' : n;
        paintBrowseShell(cache.facets);
        loadBrowse(true);
        break;
      case 'expand': {
        // 长诗在列表里先折叠，点这里就地展开，不再跳去详情页
        var card = el.closest('.feed-item');
        var f = card && card.querySelector('.full');
        if (f) f.classList.remove('clamp');
        el.style.display = 'none';
        break;
      }
      case 'dtab':
        view.detailTab = parseInt(el.getAttribute('data-i'), 10) || 0;
        syncTabs();
        repaintPanel();          // 标签条不动，只换下面那块内容
        break;
      case 'ruby':
        view.ruby = !view.ruby;
        var v = $('verse');
        if (v) v.classList.toggle('ruby-on', view.ruby);
        el.classList.toggle('on', view.ruby);
        break;
      case 'fs':
        view.fsStep = (view.fsStep + 1) % FS_STEPS.length;
        document.documentElement.style.setProperty('--fs', FS_STEPS[view.fsStep]);
        break;
      case 'toyiwen':
        view.detailTab = 0;
        syncTabs();
        repaintPanel();
        var box2 = $('yw-box');
        if (box2) box2.scrollIntoView({ behavior: 'smooth', block: 'center' });
        break;
      case 'speak':
        var sid = el.getAttribute('data-id');
        speak(sid);
        break;
      case 'dosearch':
        doSearch();
        break;
      case 'q':
        var input = $('q');
        if (input) { input.value = el.getAttribute('data-q'); doSearch(); }
        break;
      case 'clearsearch':
        searchState.results = null;
        if ($('q')) $('q').value = '';
        paintSearch();
        break;
      case 'dozi':
        var zi = ($('zc') && $('zc').value || '').trim();
        if (zi) push('zi', { c: zi.slice(0, 1) });
        else toast('输入一个汉字');
        break;
      default:
        break;
    }
  });

  // 软键盘回车即检索
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    if (e.target && e.target.id === 'q') doSearch();
    if (e.target && e.target.id === 'zc') {
      var v = e.target.value.trim();
      if (v) push('zi', { c: v.slice(0, 1) });
    }
  });

  /** 诵读：整篇交给原生 TTS，标题与作者一起念出来。 */
  function speak(id) {
    Bridge.call('speak', { id: id }).then(function (r) {
      if (r && r.ok === false) toast(r.msg || '本机没有可用的中文语音引擎');
    }).catch(function () { toast('诵读失败'); });
  }

  /** 供物理返回键调用；返回 true 表示前端已消费这次返回。 */
  window.__back = function () {
    if (state.stack.length) { pop(); return true; }
    if (state.tab !== 'home') { show('home'); return true; }
    return false;
  };

  /* ---------------------------------------------------------------- 启动 */

  bindPagers();
  render();
})();
