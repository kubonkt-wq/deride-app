import http.server
import socketserver
import sqlite3
import urllib.parse
import json
import csv
import io
import os
from datetime import datetime

# ==========================================
# 0. Vercel対応 データベース保存先設定
# Vercelでは '/tmp' フォルダのみ書き込みが許可されています
# ==========================================
if os.environ.get('VERCEL'):
    DB_PATH = '/tmp/platform.db'
else:
    DB_PATH = 'platform.db'

# ==========================================
# 1. データベースの準備
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY, shop_id INTEGER, category TEXT, title TEXT, price INTEGER, 
        status TEXT, description TEXT, created_at TEXT, image_data TEXT,
        brand TEXT, item_condition TEXT, shipping_fee TEXT, shipping_method TEXT, shipping_area TEXT, shipping_days TEXT,
        likes_count INTEGER DEFAULT 0
    )""")
    try:
        c.execute("ALTER TABLE items ADD COLUMN likes_count INTEGER DEFAULT 0")
    except: pass
    c.execute("""CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY, item_id INTEGER, seller_shop_id INTEGER, buyer_shop_id INTEGER, 
        deal_price INTEGER, fee_amount INTEGER, closed_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY, item_id INTEGER, shop_id INTEGER, message TEXT, created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY, pref TEXT, district TEXT, branch TEXT, group_name TEXT, name TEXT
    )""")
    
    # 店舗マスター初期データ（空の場合に投入）
    c.execute("SELECT count(*) FROM shops")
    if c.fetchone()[0] == 0:
        default_shops = [
            (1, '愛知県', '名古屋市', '名古屋中支部', '栄班', '中日新聞 栄専売店'),
            (2, '愛知県', '名古屋市', '名古屋北支部', '名北班', '中日新聞 名北専売店'),
            (3, '愛知県', '尾張地区', '一宮支部', '一宮班', '中日新聞 一宮専売店'),
            (4, '岐阜県', '岐阜地区', '岐阜南支部', '岐阜南班', '中日新聞 岐阜南専売店'),
            (5, '三重県', '三重地区', '津支部', '津班', '中日新聞 津専売店')
        ]
        c.executemany("INSERT INTO shops VALUES (?, ?, ?, ?, ?, ?)", default_shops)
        
    # デモ用初期出品データ（空の場合に投入）
    c.execute("SELECT count(*) FROM items")
    if c.fetchone()[0] == 0:
        default_items = [
            (1, 4, 'バイク', 'スーパーカブ50 プロ（大型前カゴ・リアBOX付）', 85000, '出品中', '走行距離 24,000km。エンジン良好、定期オイル交換済み。タイヤ溝十分あります。', '2026-10-25 10:00', '', 'ホンダ', '未使用に近い', '送料込み', '直接引き取り', '岐阜県', '1〜2日で発送', 3),
            (2, 5, '部品', 'プレスカブ用 レッグシールド＆フロントキャリア純正品', 12000, '出品中', '予備で保管していた純正新品パーツです。割れや目立つ傷はありません。', '2026-10-26 14:30', '', 'ホンダ', '新品', '送料込み', '陸送・宅配便', '三重県', '2〜3日で発送', 5)
        ]
        c.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", default_items)

    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. PWA（アプリ化）設定データ
# ==========================================
APP_ICON_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%231e40af'/><text x='50%' y='48%' font-size='42' text-anchor='middle' dominant-baseline='central'>🏍️</text><text x='50%' y='80%' font-size='15' font-weight='bold' fill='white' text-anchor='middle'>でらいど</text></svg>"""

MANIFEST_DATA = json.dumps({
    "name": "中日新聞 バイクマーケット でらいど",
    "short_name": "でらいど",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#1e40af",
    "theme_color": "#1e40af",
    "icons": [
        {
            "src": "/app-icon.svg",
            "sizes": "192x192 512x512",
            "type": "image/svg+xml",
            "purpose": "any maskable"
        }
    ]
}, ensure_ascii=False)

SW_JS = """
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { self.clients.claim(); });
self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request).catch(() => caches.match(e.request))); });
"""

# ==========================================
# 3. 共通レイアウト
# ==========================================
BASE_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>でらいど - 中日新聞専売店 バイクマーケット</title>
  
  <link rel="manifest" href="/manifest.json">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="でらいど">
  <link rel="apple-touch-icon" href="/app-icon.svg">
  <link rel="icon" type="image/svg+xml" href="/app-icon.svg">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#1e40af">

  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
      });
    }
  </script>
</head>
<body class="bg-gray-100 text-gray-800 pb-28 select-none">
  <!-- 上部ヘッダー -->
  <header class="bg-blue-800 text-white sticky top-0 z-40 shadow pt-[env(safe-area-inset-top)]">
    <div class="max-w-4xl mx-auto px-4 py-3 flex justify-between items-center">
      <a href="/" class="font-bold text-base md:text-lg tracking-wide flex items-center gap-2">
        <span class="bg-yellow-400 text-blue-900 text-xs px-2 py-0.5 rounded-full font-black">公式</span>
        <span>でらいど</span>
        <span class="text-xs text-blue-200 font-normal hidden sm:inline">| 中日新聞 専売店マーケット</span>
      </a>
      <a href="/admin/deals" class="text-xs bg-yellow-400 text-blue-950 font-bold px-2.5 py-1.5 rounded-lg shadow hover:bg-yellow-300 transition flex items-center gap-1">
        <span>📊</span> 請求・管理
      </a>
    </div>
  </header>

  <!-- メイン画面 -->
  <main class="max-w-4xl mx-auto p-4">
    __CONTENT__
  </main>

  <!-- 下部固定ナビゲーションバー（5項目） -->
  <nav class="fixed bottom-0 left-0 right-0 z-50 bg-white/95 backdrop-blur border-t border-gray-200 shadow-[0_-2px_10px_rgba(0,0,0,0.06)] pb-[env(safe-area-inset-bottom)]">
    <div class="max-w-md mx-auto grid grid-cols-5 h-16">
      <a href="/" class="flex flex-col items-center justify-center text-xs transition __HOME_CLS__ active:scale-95">
        <span class="text-lg leading-none">🏠</span>
        <span class="mt-1 text-[9px]">ホーム</span>
      </a>
      <a href="/likes" class="flex flex-col items-center justify-center text-xs transition __LIKES_CLS__ active:scale-95">
        <span class="text-lg leading-none">❤️</span>
        <span class="mt-1 text-[9px]">いいね</span>
      </a>
      <a href="/sell" class="flex flex-col items-center justify-center text-xs transition __SELL_CLS__ active:scale-95">
        <span class="text-lg leading-none">📷</span>
        <span class="mt-1 text-[9px]">出品</span>
      </a>
      <a href="/mypage" class="flex flex-col items-center justify-center text-xs transition __MYPAGE_CLS__ active:scale-95">
        <span class="text-lg leading-none">👤</span>
        <span class="mt-1 text-[9px]">マイページ</span>
      </a>
      <a href="/admin/deals" class="flex flex-col items-center justify-center text-xs transition __ADMIN_CLS__ active:scale-95">
        <span class="text-lg leading-none">📊</span>
        <span class="mt-1 text-[9px]">管理・Excel</span>
      </a>
    </div>
  </nav>
</body>
</html>"""

def render_page(content, active_tab="home"):
    inactive_cls = "text-gray-400 hover:text-gray-600 font-medium"
    active_cls = "text-blue-600 font-bold"

    home_cls = active_cls if active_tab == "home" else inactive_cls
    likes_cls = active_cls if active_tab == "likes" else inactive_cls
    sell_cls = active_cls if active_tab == "sell" else inactive_cls
    mypage_cls = active_cls if active_tab == "mypage" else inactive_cls
    admin_cls = active_cls if active_tab == "admin" else inactive_cls

    html = BASE_HTML.replace("__CONTENT__", content)
    html = html.replace("__HOME_CLS__", home_cls)
    html = html.replace("__LIKES_CLS__", likes_cls)
    html = html.replace("__SELL_CLS__", sell_cls)
    html = html.replace("__MYPAGE_CLS__", mypage_cls)
    html = html.replace("__ADMIN_CLS__", admin_cls)
    return html

def build_item_cards(items):
    items_html = ""
    for item in items:
        color = "bg-green-100 text-green-800" if item[2] == "バイク" else "bg-orange-100 text-orange-800"
        
        img_src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' viewBox='0 0 24 24' fill='none' stroke='%23ccc' stroke-width='1'><rect width='18' height='18' x='3' y='3' rx='2'/><circle cx='8.5' cy='8.5' r='1.5'/></svg>"
        raw_img = item[8]
        img_count_badge = ""
        if raw_img:
            if raw_img.startswith('['):
                try:
                    imgs = json.loads(raw_img)
                    if imgs: 
                        img_src = imgs[0]
                        img_count_badge = f'<span class="absolute bottom-1 right-1 bg-black/60 text-white text-[9px] px-1.5 py-0.5 rounded-md font-bold">📷 {len(imgs)}</span>'
                except: pass
            else:
                img_src = raw_img
        
        status_badge = ""
        if item[5] == "成約済み":
            status_badge = '<div class="absolute inset-0 bg-black/50 flex items-center justify-center"><span class="bg-red-600 text-white font-bold text-sm px-3 py-1 rounded">成約済み</span></div>'
        
        shop_display_name = item[15] if item[5] == "成約済み" else "🔒 出品店（成約後に開示）"
        likes_val = item[18] if len(item) > 18 and item[18] else 0
        likes_display = f'<span class="text-xs text-pink-600 font-semibold flex items-center gap-0.5">❤️ {likes_val}</span>' if likes_val > 0 else ""

        items_html += f"""
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col justify-between hover:shadow-md transition">
          <div class="w-full h-44 bg-gray-100 flex items-center justify-center overflow-hidden relative">
            <img src="{img_src}" alt="{item[3]}" class="w-full h-full object-cover">
            {img_count_badge}
            {status_badge}
          </div>
          <div class="p-3 flex-1 flex flex-col justify-between">
            <div>
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs px-2 py-0.5 rounded font-semibold {color}">{item[2]}</span>
                <span class="text-xs text-gray-400">{item[7][:10]}</span>
              </div>
              <h3 class="font-bold text-gray-900 text-sm md:text-base line-clamp-1">{item[3]}</h3>
              <p class="text-xs text-gray-500 mt-0.5">{item[16]} {item[17]}<br><span class="font-semibold text-gray-700">{shop_display_name}</span></p>
            </div>
            <div class="mt-3 pt-2 border-t flex items-center justify-between">
              <div>
                <span class="text-lg font-black text-red-600">¥{item[4]:,}</span>
              </div>
              <div class="flex items-center gap-2">
                {likes_display}
                <a href="/items/{item[0]}" class="bg-blue-600 text-white text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-blue-700 shadow-sm active:scale-95 transition">商品を見る</a>
              </div>
            </div>
          </div>
        </div>
        """
    return items_html

# --- A. ホーム画面 ---
def render_home():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT i.id, i.shop_id, i.category, i.title, i.price, i.status, i.description, i.created_at, i.image_data, 
               i.brand, i.item_condition, i.shipping_fee, i.shipping_method, i.shipping_area, i.shipping_days, 
               s.name, s.pref, s.branch, COALESCE(i.likes_count, 0)
        FROM items i JOIN shops s ON i.shop_id = s.id 
        ORDER BY i.id DESC
    """)
    items = c.fetchall()
    conn.close()

    items_html = build_item_cards(items)
    if not items_html:
        items_html = '<div class="col-span-full text-center py-16 bg-white rounded-xl border border-dashed border-gray-300 text-gray-400"><p class="text-sm font-bold">出品中の車両・部品はまだありません。</p></div>'

    content = f"""
    <!-- LP上部メインバナー画像 -->
    <div class="rounded-2xl overflow-hidden shadow-md mb-5 border border-blue-200 bg-blue-50">
      <img src="/banner.jpg" alt="でらいど 新聞販売店専用アプリ" class="w-full h-auto object-cover block">
    </div>

    <div class="flex items-center justify-between mb-3">
      <h2 class="text-sm md:text-base font-bold text-gray-900 flex items-center gap-1.5">
        <span>🏍️</span>
        <span>出品車両・部品一覧</span>
        <span class="text-xs font-normal text-gray-500">({len(items)}件)</span>
      </h2>
      <a href="/sell" class="bg-blue-600 text-white font-bold text-xs px-3.5 py-1.5 rounded-xl shadow hover:bg-blue-700 transition flex items-center gap-1">
        <span>📷</span> 出品する
      </a>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
      {items_html}
    </div>
    """
    return render_page(content, active_tab="home")

# --- B. いいね画面 ---
def render_likes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT i.id, i.shop_id, i.category, i.title, i.price, i.status, i.description, i.created_at, i.image_data, 
               i.brand, i.item_condition, i.shipping_fee, i.shipping_method, i.shipping_area, i.shipping_days, 
               s.name, s.pref, s.branch, COALESCE(i.likes_count, 0)
        FROM items i JOIN shops s ON i.shop_id = s.id 
        WHERE COALESCE(i.likes_count, 0) > 0
        ORDER BY i.likes_count DESC, i.id DESC
    """)
    items = c.fetchall()
    conn.close()

    items_html = build_item_cards(items)
    if not items_html:
        items_html = """
        <div class="col-span-full text-center py-16 bg-white rounded-xl border border-dashed border-pink-200 text-gray-400">
          <span class="text-4xl block mb-2">❤️</span>
          <p class="text-sm font-bold text-gray-700">まだ「いいね」された商品はありません</p>
          <a href="/" class="inline-block mt-4 px-4 py-2 bg-blue-600 text-white font-bold text-xs rounded-lg shadow hover:bg-blue-700">商品を探しにいく</a>
        </div>
        """

    content = f"""
    <div class="mb-4">
      <h2 class="text-base font-bold text-gray-900 flex items-center gap-1.5">
        <span class="text-pink-600 text-lg">❤️</span>
        <span>いいね！された人気商品</span>
        <span class="text-xs font-normal text-gray-500">({len(items)}件)</span>
      </h2>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
      {items_html}
    </div>
    """
    return render_page(content, active_tab="likes")

# --- C. 出品・編集画面 ---
def render_sell(edit_item_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, pref, district, branch, group_name, name FROM shops ORDER BY pref, district, branch, group_name, name")
    raw_shops = c.fetchall()
    shops_data = [{"id": r[0], "p": r[1] or "", "d": r[2] or "", "b": r[3] or "", "g": r[4] or "", "n": r[5] or ""} for r in raw_shops]
    shops_json = json.dumps(shops_data, ensure_ascii=False)

    item_to_edit = None
    if edit_item_id:
        c.execute("SELECT id, shop_id, category, title, price, description, brand, item_condition, shipping_fee, shipping_method, shipping_area, shipping_days, image_data FROM items WHERE id=?", (edit_item_id,))
        item_to_edit = c.fetchone()
    conn.close()

    is_edit = item_to_edit is not None
    form_action = "/items/update" if is_edit else "/items/create"
    page_title = "✏️ 出品情報を編集する" if is_edit else "📷 でらいど に出品する"

    item_id_val = item_to_edit[0] if is_edit else ""
    title_val = item_to_edit[3] if is_edit else ""
    price_val = item_to_edit[4] if is_edit else ""
    desc_val = item_to_edit[5] if is_edit else ""
    cat_val = item_to_edit[2] if is_edit else "バイク"
    brand_val = item_to_edit[6] if is_edit else "ホンダ"
    cond_val = item_to_edit[7] if is_edit else "未使用に近い"
    img_json_val = item_to_edit[12] if is_edit and item_to_edit[12] else ""

    template = f"""
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-4 md:p-6 mb-6">
      <div class="border-b pb-3 mb-4">
        <h1 class="text-base md:text-lg font-black text-gray-900 flex items-center gap-2">
          <span>{page_title}</span>
        </h1>
      </div>

      <form action="{form_action}" method="post" class="space-y-4">
        <input type="hidden" name="item_id" value="{item_id_val}">
        
        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block text-xs font-bold text-gray-700">写真を追加（スマホで最大10枚）</label>
            <span id="imgCounter" class="text-xs text-gray-500 font-normal">0 / 10枚</span>
          </div>
          <input type="file" id="filePicker" accept="image/*" multiple class="block w-full text-xs text-gray-500 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-blue-100 file:text-blue-700 font-bold cursor-pointer">
          <input type="hidden" name="image_data_json" id="imageDataField" value='{img_json_val}'>
          <div id="imagePreviewContainer" class="mt-2 hidden flex flex-wrap gap-2 p-2 bg-gray-50 rounded-lg border border-dashed border-gray-300"></div>
        </div>

        <div class="bg-blue-50/70 p-3 rounded-xl border border-blue-200 space-y-2">
          <label class="block text-xs font-bold text-blue-900">出品店舗を選択（所属ツリー）</label>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div>
              <label class="block text-[10px] text-gray-600 mb-0.5">① 県</label>
              <select id="treePref" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
            </div>
            <div id="districtBox">
              <label class="block text-[10px] text-gray-600 mb-0.5">② 地区</label>
              <select id="treeDistrict" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
            </div>
            <div>
              <label class="block text-[10px] text-gray-600 mb-0.5">③ 支部</label>
              <select id="treeBranch" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
            </div>
            <div id="groupBox">
              <label class="block text-[10px] text-gray-600 mb-0.5">④ 班</label>
              <select id="treeGroup" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
            </div>
          </div>
          <div>
            <label class="block text-[10px] text-gray-600 mb-0.5">⑤ 店舗名</label>
            <select id="treeShop" name="shop_id" class="w-full border rounded-lg p-2 text-sm font-bold bg-white text-blue-900" required>
              <option value="">↑ 上の県・支部を選択してください</option>
            </select>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3 mt-4">
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">カテゴリ</label>
            <select name="category" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option {"selected" if cat_val=="バイク" else ""}>バイク</option>
              <option {"selected" if cat_val=="部品" else ""}>部品</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">ブランド</label>
            <select name="brand" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option {"selected" if brand_val=="ホンダ" else ""}>ホンダ</option>
              <option {"selected" if brand_val=="ヤマハ" else ""}>ヤマハ</option>
              <option {"selected" if brand_val=="その他" else ""}>その他</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">商品状態</label>
            <select name="item_condition" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option {"selected" if cond_val=="新品" else ""}>新品</option>
              <option {"selected" if cond_val=="未使用に近い" else ""}>未使用に近い</option>
              <option {"selected" if cond_val=="傷や汚れあり" else ""}>傷や汚れあり</option>
              <option {"selected" if cond_val=="状態が悪い" else ""}>状態が悪い</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">配送料の負担</label>
            <select name="shipping_fee" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option>送料込み</option><option>着払い</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">配送方法</label>
            <select name="shipping_method" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option>未定</option><option>直接引き取り</option><option>陸送・宅配便</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">発送元の地域</label>
            <select name="shipping_area" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option>愛知県</option><option>岐阜県</option><option>三重県</option><option>その他</option>
            </select>
          </div>
          <div class="col-span-2">
            <label class="block text-xs font-bold text-gray-700 mb-1">発送までの日数</label>
            <select name="shipping_days" class="w-full border rounded-lg p-2 text-sm bg-white">
              <option>1〜2日で発送</option><option>2〜3日で発送</option><option>4〜7日で発送</option>
            </select>
          </div>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-700 mb-1">商品タイトル</label>
          <input type="text" name="title" value="{title_val}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="例: スーパーカブ50プロ 配達ボックス付き" required>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-700 mb-1">希望価格 (円)</label>
          <input type="number" name="price" id="inputPrice" value="{price_val}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="例: 85000" required>
          <div id="feeEstimation" class="mt-2 p-2.5 bg-gray-50 rounded-lg border border-gray-200 text-xs space-y-1">
            <div class="flex justify-between text-gray-600">
              <span>でらいど手数料 (10%):</span>
              <span id="estFee" class="text-red-600 font-bold">¥0</span>
            </div>
            <div class="flex justify-between text-green-700 font-bold border-t pt-1">
              <span>手取予想金額:</span>
              <span id="estNet" class="text-sm">¥0</span>
            </div>
          </div>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-700 mb-1">車両状態・備考</label>
          <textarea name="description" class="w-full border rounded-lg p-2 text-sm h-24" required>{desc_val}</textarea>
        </div>

        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl text-sm shadow-md transition active:scale-95">
          {"更新内容を保存する" if is_edit else "でらいどに出品登録する"}
        </button>
      </form>
    </div>

    <script>
      const allShops = __SHOPS_JSON__;
      const prefEl = document.getElementById('treePref');
      const distEl = document.getElementById('treeDistrict');
      const distBox = document.getElementById('districtBox');
      const branchEl = document.getElementById('treeBranch');
      const groupEl = document.getElementById('treeGroup');
      const groupBox = document.getElementById('groupBox');
      const shopEl = document.getElementById('treeShop');

      const prefs = [...new Set(allShops.map(s => s.p).filter(Boolean))];
      prefEl.innerHTML = '<option value="">県を選択</option>' + prefs.map(p => '<option value="' + p + '">' + p + '</option>').join('');

      prefEl.addEventListener('change', () => {{
        const selPref = prefEl.value;
        distEl.innerHTML = '<option value="">地区を選択</option>';
        branchEl.innerHTML = '<option value="">支部を選択</option>';
        groupEl.innerHTML = '<option value="">班を選択</option>';
        shopEl.innerHTML = '<option value="">店舗を選択</option>';

        if (!selPref) return;
        const filtered = allShops.filter(s => s.p === selPref);
        const dists = [...new Set(filtered.map(s => s.d).filter(Boolean))];

        if (dists.length === 0) {{
          distBox.classList.add('hidden');
          loadBranches(selPref, "");
        }} else {{
          distBox.classList.remove('hidden');
          distEl.innerHTML = '<option value="">地区を選択</option>' + dists.map(d => '<option value="' + d + '">' + d + '</option>').join('');
        }}
      }});

      distEl.addEventListener('change', () => loadBranches(prefEl.value, distEl.value));

      function loadBranches(pref, dist) {{
        branchEl.innerHTML = '<option value="">支部を選択</option>';
        groupEl.innerHTML = '<option value="">班を選択</option>';
        shopEl.innerHTML = '<option value="">店舗を選択</option>';

        const filtered = allShops.filter(s => s.p === pref && (!dist || s.d === dist));
        const branches = [...new Set(filtered.map(s => s.b).filter(Boolean))];
        branchEl.innerHTML = '<option value="">支部を選択</option>' + branches.map(b => '<option value="' + b + '">' + b + '</option>').join('');
      }}

      branchEl.addEventListener('change', () => {{
        const selBranch = branchEl.value;
        groupEl.innerHTML = '<option value="">班を選択</option>';
        shopEl.innerHTML = '<option value="">店舗を選択</option>';
        if (!selBranch) return;

        const filtered = allShops.filter(s => s.p === prefEl.value && (!distEl.value || s.d === distEl.value) && s.b === selBranch);
        const groups = [...new Set(filtered.map(s => s.g).filter(Boolean))];

        if (groups.length === 0) {{
          groupBox.classList.add('hidden');
          loadShops(prefEl.value, distEl.value, selBranch, "");
        }} else {{
          groupBox.classList.remove('hidden');
          groupEl.innerHTML = '<option value="">班を選択</option>' + groups.map(g => '<option value="' + g + '">' + g + '</option>').join('');
        }}
      }});

      groupEl.addEventListener('change', () => loadShops(prefEl.value, distEl.value, branchEl.value, groupEl.value));

      function loadShops(pref, dist, branch, group) {{
        const filtered = allShops.filter(s => s.p === pref && (!dist || s.d === dist) && s.b === branch && (!group || s.g === group));
        shopEl.innerHTML = '<option value="">店舗を選択してください</option>' + filtered.map(s => '<option value="' + s.id + '">' + s.n + '</option>').join('');
      }}

      const priceInp = document.getElementById('inputPrice');
      function calcFee() {{
        const val = parseInt(priceInp.value, 10);
        if (!isNaN(val) && val > 0) {{
          document.getElementById('estFee').innerText = '¥' + Math.floor(val * 0.10).toLocaleString();
          document.getElementById('estNet').innerText = '¥' + (val - Math.floor(val * 0.10)).toLocaleString();
        }}
      }}
      priceInp.addEventListener('input', calcFee);
      calcFee();

      document.getElementById('filePicker').addEventListener('change', function(e) {{
        const files = e.target.files;
        if (!files || files.length === 0) return;
        const fileCount = Math.min(files.length, 10);
        const previewContainer = document.getElementById('imagePreviewContainer');
        previewContainer.innerHTML = '<div class="text-xs text-gray-500 w-full p-2">画像処理中...</div>';
        previewContainer.classList.remove('hidden');
        
        const imageDataArray = new Array(fileCount);
        let processedCount = 0;
        
        for (let i = 0; i < fileCount; i++) {{
          const file = files[i];
          const reader = new FileReader();
          reader.onload = function(event) {{
            const img = new Image();
            img.onload = function() {{
              const canvas = document.createElement('canvas');
              const maxDim = 800;
              let w = img.width, h = img.height;
              if (w > h && w > maxDim) {{ h *= maxDim / w; w = maxDim; }}
              else if (h > maxDim) {{ w *= maxDim / h; h = maxDim; }}
              canvas.width = w; canvas.height = h;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(img, 0, 0, w, h);
              imageDataArray[i] = canvas.toDataURL('image/jpeg', 0.65);
              processedCount++;
              
              if (processedCount === fileCount) {{
                document.getElementById('imageDataField').value = JSON.stringify(imageDataArray);
                document.getElementById('imgCounter').innerText = `${{fileCount}} / 10枚`;
                previewContainer.innerHTML = '';
                imageDataArray.forEach((src, idx) => {{
                  const div = document.createElement('div');
                  div.className = 'relative h-14 w-14 rounded border overflow-hidden';
                  div.innerHTML = `<img src="${{src}}" class="h-full w-full object-cover">`;
                  previewContainer.appendChild(div);
                }});
              }}
            }};
            img.src = event.target.result;
          }};
          reader.readAsDataURL(file);
        }}
      }});
    </script>
    """
    content = template.replace("__SHOPS_JSON__", shops_json)
    return render_page(content, active_tab="sell")

# --- D. 商品詳細画面 ---
def render_detail(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT i.id, i.shop_id, i.category, i.title, i.price, i.status, i.description, i.created_at, i.image_data, 
               i.brand, i.item_condition, i.shipping_fee, i.shipping_method, i.shipping_area, i.shipping_days, 
               s.name, s.pref, s.branch, s.district, s.group_name, COALESCE(i.likes_count, 0)
        FROM items i JOIN shops s ON i.shop_id = s.id 
        WHERE i.id=?
    """, (item_id,))
    item = c.fetchone()
    
    c.execute("SELECT comments.message, comments.created_at, shops.name FROM comments JOIN shops ON comments.shop_id = shops.id WHERE comments.item_id=? ORDER BY comments.id ASC", (item_id,))
    comments = c.fetchall()

    c.execute("""
        SELECT d.deal_price, d.fee_amount, d.closed_at, b.name 
        FROM deals d JOIN shops b ON d.buyer_shop_id = b.id 
        WHERE d.item_id=?
    """, (item_id,))
    deal = c.fetchone()
    
    c.execute("SELECT id, pref, branch, name FROM shops ORDER BY pref, branch, name")
    all_shops = c.fetchall()
    conn.close()

    if not item: return render_page("<p>商品が見つかりません。</p>", active_tab="home")
    
    price = item[4]
    fee_10pct = int(price * 0.10)
    net_income = price - fee_10pct
    likes_count = item[20]
    is_closed = item[5] == "成約済み"

    seller_name_display = item[15] if is_closed else "🔒 出品店（成約後に開示）"

    buyer_options = "".join([f'<option value="{s[0]}">[{s[1]} {s[2]}] {s[3]}</option>' for s in all_shops if s[0] != item[1]])
    commenter_options = "".join([f'<option value="{s[0]}">[{s[1]} {s[2]}] {s[3]}</option>' for s in all_shops])

    raw_img = item[8]
    images = []
    if raw_img:
        if raw_img.startswith('['):
            try: images = json.loads(raw_img)
            except: pass
        else:
            images = [raw_img]

    img_html = ""
    if images:
        thumbs_html = "".join([
            f'<img src="{img}" onclick="document.getElementById(\'mainDetailImg\').src=this.src;" class="thumb-item w-16 h-12 object-cover rounded-md border-2 cursor-pointer flex-shrink-0" />'
            for img in images
        ])
        img_html = f"""
        <div class="mb-4">
          <div class="w-full bg-black rounded-lg overflow-hidden flex items-center justify-center h-64 md:h-96 relative shadow">
            <img id="mainDetailImg" src="{images[0]}" class="w-full h-full object-contain">
          </div>
          {f'<div class="flex overflow-x-auto gap-2 mt-2 pb-2 p-1 bg-white rounded-lg border">{thumbs_html}</div>' if len(images) > 1 else ""}
        </div>
        """

    comments_html = ""
    for com in comments:
        is_seller = com[2] == item[15]
        badge = '<span class="ml-1 text-[10px] bg-blue-600 text-white px-1 py-0.5 rounded">出品店</span>' if is_seller else ''
        bg_cls = 'bg-blue-50 border-blue-200' if is_seller else 'bg-gray-50 border-gray-200'
        sender_disp = com[2] if (is_closed or is_seller) else "質問店舗"
        comments_html += f"""
        <div class="{bg_cls} p-2.5 rounded-lg border mb-2 text-xs">
          <div class="flex justify-between items-center mb-1 font-bold text-gray-700">
            <span>{sender_disp} {badge}</span>
            <span class="text-[10px] text-gray-400 font-normal">{com[1]}</span>
          </div>
          <p class="text-gray-800 whitespace-pre-wrap">{com[0]}</p>
        </div>"""

    seller_payout_box = f"""
    <div class="bg-blue-50 border border-blue-200 rounded-xl p-3.5 space-y-2 text-xs">
      <span class="font-bold text-blue-900 block">💰 受取金額（でらいど手数料10%差引後）</span>
      <div class="bg-white rounded-lg p-2.5 border space-y-1">
        <div class="flex justify-between text-gray-600"><span>売値:</span><span class="font-bold">¥{price:,}</span></div>
        <div class="flex justify-between text-red-600"><span>手数料(10%):</span><span>-¥{fee_10pct:,}</span></div>
        <div class="border-t pt-1 flex justify-between font-black text-green-700"><span>手取受取額:</span><span>¥{net_income:,}</span></div>
      </div>
    </div>
    """

    deal_action_box = ""
    if not is_closed:
        deal_action_box = f"""
        <div class="bg-yellow-50 border border-yellow-300 rounded-xl p-3.5 space-y-2">
          <h4 class="font-bold text-xs text-gray-900">商談成立時の成約登録</h4>
          <form action="/deals/close" method="post" class="space-y-2">
            <input type="hidden" name="item_id" value="{item[0]}">
            <input type="hidden" name="seller_shop_id" value="{item[1]}">
            <input type="hidden" name="price" value="{item[4]}">
            <select name="buyer_shop_id" class="w-full border rounded-lg p-2 text-xs bg-white">{buyer_options}</select>
            <button type="submit" class="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-2 rounded-lg text-xs shadow">この店舗との成約を確定する（手数料10%）</button>
          </form>
        </div>
        """

    status_tag = f'<span class="text-xs px-2.5 py-0.5 rounded-full font-bold bg-red-600 text-white">成約済み</span>' if is_closed else '<span class="text-xs px-2.5 py-0.5 rounded-full font-bold bg-green-600 text-white">出品中</span>'

    content = f"""
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <a href="/" class="text-xs text-blue-600 font-bold hover:underline">← でらいど トップに戻る</a>
        <span class="text-xs text-gray-400">ID: #{item[0]}</span>
      </div>

      <div class="bg-white rounded-xl shadow-sm border p-4">
        {img_html}
        <div class="flex items-center justify-between">
          <span class="text-xs px-2 py-0.5 rounded font-bold bg-gray-100 text-gray-700">{item[2]}</span>
          {status_tag}
        </div>
        <h1 class="text-xl font-black mt-2 text-gray-900">{item[3]}</h1>
        
        <div class="mt-3 pt-3 border-t flex items-center justify-between">
          <div>
            <span class="text-xs text-gray-500 block">販売価格（税込）</span>
            <span class="text-2xl font-black text-red-600">¥{item[4]:,}</span>
          </div>
          
          <form action="/items/like" method="post" class="inline">
            <input type="hidden" name="item_id" value="{item[0]}">
            <button type="submit" class="flex items-center gap-1.5 px-4 py-2 rounded-full border border-pink-200 bg-pink-50 text-pink-600 font-bold text-xs shadow-sm">
              <span>❤️ いいね！</span>
              <span class="bg-white px-2 py-0.5 rounded-full font-black border text-xs">{likes_count}</span>
            </button>
          </form>
        </div>
        
        <div class="mt-4 pt-3 border-t text-xs space-y-1.5 text-gray-600">
          <p><strong class="text-gray-800">出品地域:</strong> {item[16]} {item[17]}</p>
          <p><strong class="text-gray-800">出品店舗:</strong> <span class="font-bold text-blue-900">{seller_name_display}</span></p>
          <p><strong class="text-gray-800">登録日:</strong> {item[7]}</p>
          <div class="bg-gray-50 p-3 rounded-lg border mt-2 whitespace-pre-wrap text-sm text-gray-800 leading-relaxed">{item[6]}</div>
        </div>
      </div>

      <div class="bg-white rounded-xl shadow-sm border p-4">
        <h3 class="font-bold text-sm mb-1 text-blue-900">💬 質問・商談連絡</h3>
        <div class="max-h-64 overflow-y-auto mb-3">{comments_html or '<p class="text-xs text-gray-400 text-center py-2">質問はありません</p>'}</div>
        <form action="/comments/create" method="post" class="space-y-2 pt-2 border-t">
          <input type="hidden" name="item_id" value="{item[0]}">
          <select name="shop_id" class="w-full border rounded-lg p-2 text-xs bg-white">{commenter_options}</select>
          <textarea name="message" placeholder="質問・商談内容を入力..." class="w-full border rounded-lg p-2 text-xs h-16" required></textarea>
          <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded-lg text-xs hover:bg-blue-700 shadow">コメント送信</button>
        </form>
      </div>

      <details class="bg-gray-50 border rounded-xl overflow-hidden text-xs text-gray-700">
        <summary class="p-3.5 font-bold cursor-pointer flex items-center justify-between bg-gray-100 hover:bg-gray-200">
          <span>⚙️ 出品店舗専用メニュー（修正・成約確定・削除）</span>
          <span class="text-[10px] text-gray-400">タップして開く ▼</span>
        </summary>
        <div class="p-4 space-y-4 bg-white border-t">
          <div class="flex gap-2">
            <a href="/items/{item[0]}/edit" class="flex-1 text-center bg-amber-500 hover:bg-amber-600 text-white font-bold py-2 rounded-lg shadow text-xs">
              ✏️ この出品情報を修正する
            </a>
          </div>
          {seller_payout_box}
          {deal_action_box}
          <div class="pt-2 border-t flex justify-end">
            <form action="/items/delete" method="post" onsubmit="return confirm('本当に削除しますか？');">
              <input type="hidden" name="item_id" value="{item[0]}">
              <button type="submit" class="text-xs text-red-600 border border-red-300 rounded-lg px-3 py-1 hover:bg-red-50 font-bold">🗑️ この出品を削除</button>
            </form>
          </div>
        </div>
      </details>
    </div>
    """
    return render_page(content, active_tab="home")

# --- E. マイページ画面 ---
def render_mypage(selected_shop_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, pref, branch, name FROM shops ORDER BY pref, branch, name")
    all_shops = c.fetchall()

    shop_options = "".join([
        f'<option value="{s[0]}" {"selected" if selected_shop_id and int(selected_shop_id)==s[0] else ""}>[{s[1]} {s[2]}] {s[3]}</option>'
        for s in all_shops
    ])

    sell_deals_html = ""
    buy_deals_html = ""

    if selected_shop_id:
        c.execute("""
            SELECT d.id, d.closed_at, i.title, b.name, d.deal_price, d.fee_amount, i.id
            FROM deals d 
            JOIN items i ON d.item_id = i.id 
            JOIN shops b ON d.buyer_shop_id = b.id
            WHERE d.seller_shop_id = ?
            ORDER BY d.closed_at DESC
        """, (selected_shop_id,))
        sell_deals = c.fetchall()

        for d in sell_deals:
            net = d[4] - d[5]
            sell_deals_html += f"""
            <div class="bg-white border rounded-xl p-3 shadow-sm flex flex-col justify-between">
              <div class="flex justify-between items-start border-b pb-2 mb-2">
                <div>
                  <span class="text-[10px] text-gray-400">{d[1][:10]} 成約</span>
                  <h4 class="font-bold text-sm text-gray-900 line-clamp-1">{d[2]}</h4>
                  <p class="text-xs text-gray-600 mt-0.5">購入店: <strong class="text-blue-900">{d[3]}</strong></p>
                </div>
                <a href="/items/{d[6]}" class="text-[10px] bg-gray-100 text-gray-700 px-2 py-1 rounded hover:bg-gray-200">詳細</a>
              </div>
              <div class="flex justify-between text-xs items-center bg-gray-50 p-2 rounded">
                <span class="text-gray-500">売値: ¥{d[4]:,} (手数料: -¥{d[5]:,})</span>
                <span class="font-black text-emerald-700 text-sm">手取: ¥{net:,}</span>
              </div>
            </div>
            """

        c.execute("""
            SELECT d.id, d.closed_at, i.title, s.name, d.deal_price, i.id
            FROM deals d 
            JOIN items i ON d.item_id = i.id 
            JOIN shops s ON d.seller_shop_id = s.id
            WHERE d.buyer_shop_id = ?
            ORDER BY d.closed_at DESC
        """, (selected_shop_id,))
        buy_deals = c.fetchall()

        for d in buy_deals:
            buy_deals_html += f"""
            <div class="bg-white border rounded-xl p-3 shadow-sm flex flex-col justify-between">
              <div class="flex justify-between items-start border-b pb-2 mb-2">
                <div>
                  <span class="text-[10px] text-gray-400">{d[1][:10]} 購入</span>
                  <h4 class="font-bold text-sm text-gray-900 line-clamp-1">{d[2]}</h4>
                  <p class="text-xs text-gray-600 mt-0.5">出品店: <strong class="text-blue-900">{d[3]}</strong></p>
                </div>
                <a href="/items/{d[5]}" class="text-[10px] bg-gray-100 text-gray-700 px-2 py-1 rounded hover:bg-gray-200">詳細</a>
              </div>
              <div class="flex justify-between text-xs items-center bg-gray-50 p-2 rounded">
                <span class="text-gray-500">購入価格(税込)</span>
                <span class="font-black text-red-600 text-sm">¥{d[4]:,}</span>
              </div>
            </div>
            """

    conn.close()

    if not sell_deals_html:
        sell_deals_html = '<p class="text-xs text-gray-400 py-6 text-center border border-dashed rounded-xl bg-white">成約した出品履歴はありません</p>'
    if not buy_deals_html:
        buy_deals_html = '<p class="text-xs text-gray-400 py-6 text-center border border-dashed rounded-xl bg-white">購入した取引履歴はありません</p>'

    content = f"""
    <div class="space-y-5">
      <div class="bg-white rounded-2xl p-4 shadow-sm border space-y-3">
        <h1 class="font-black text-base text-gray-900 flex items-center gap-2">
          <span>👤</span> でらいど 自店マイページ
        </h1>
        <form action="/mypage" method="get" class="flex gap-2">
          <select name="shop_id" class="flex-1 border rounded-xl p-2.5 text-xs bg-gray-50 font-bold" onchange="this.form.submit()">
            <option value="">▼ あなたの店舗を選択してください</option>
            {shop_options}
          </select>
          <button type="submit" class="bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow">表示</button>
        </form>
      </div>

      {f'''
      <div>
        <h3 class="font-bold text-sm text-gray-900 mb-2 flex items-center gap-1.5">
          <span>🎉</span> 自分の出品で成約した取引（売手）
        </h3>
        <div class="space-y-2">{sell_deals_html}</div>
      </div>

      <div>
        <h3 class="font-bold text-sm text-gray-900 mb-2 flex items-center gap-1.5">
          <span>🛍️</span> 自分が購入した取引（買手）
        </h3>
        <div class="space-y-2">{buy_deals_html}</div>
      </div>
      ''' if selected_shop_id else '<div class="text-center py-12 text-xs text-gray-400 bg-white rounded-2xl border border-dashed">上の選択肢から店舗を選ぶと、取引履歴が表示されます</div>'}
    </div>
    """
    return render_page(content, active_tab="mypage")

# --- F. 管理者画面 ---
def render_admin():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT deals.id, deals.closed_at, items.title, seller.name, buyer.name, deals.deal_price, deals.fee_amount 
                 FROM deals JOIN items ON deals.item_id = items.id 
                 JOIN shops as seller ON deals.seller_shop_id = seller.id 
                 JOIN shops as buyer ON deals.buyer_shop_id = buyer.id ORDER BY deals.closed_at DESC""")
    deals = c.fetchall()
    conn.close()
    
    total_fee = sum(d[6] for d in deals)
    
    rows = "".join([f"""<tr class="border-b text-xs hover:bg-gray-50">
      <td class="p-3 text-gray-600">{d[1][:10]}</td>
      <td class="p-3 font-bold text-gray-800">{d[2]}</td>
      <td class="p-3 text-gray-700">
        <span class="text-[10px] text-blue-600 bg-blue-50 px-1 rounded border">売手</span> {d[3]}<br>
        <span class="text-[10px] text-green-600 bg-green-50 px-1 rounded border mt-1 inline-block">買手</span> {d[4]}
      </td>
      <td class="p-3 text-right">¥{d[5]:,}</td>
      <td class="p-3 text-right font-bold text-red-600">¥{d[6]:,}</td>
      <td class="p-3 text-right font-black text-emerald-700">¥{(d[5] - d[6]):,}</td>
    </tr>""" for d in deals]) or '<tr><td colspan="6" class="text-center p-8 text-sm text-gray-400 border-b">成約履歴はまだありません</td></tr>'
    
    content = f"""
    <div class="space-y-4 mb-6">
      <div class="bg-gradient-to-r from-emerald-600 to-teal-700 rounded-2xl p-5 text-white shadow-md flex flex-col sm:flex-row items-center justify-between gap-4">
        <div>
          <span class="text-xs bg-emerald-800/60 px-2 py-0.5 rounded font-bold uppercase tracking-wider">Excel連携機能</span>
          <h2 class="text-lg font-black mt-1">成約データの一括ダウンロード</h2>
        </div>
        <a href="/admin/deals/download" class="w-full sm:w-auto text-center px-6 py-3.5 bg-yellow-400 hover:bg-yellow-300 text-emerald-950 font-black text-sm rounded-xl shadow-lg transition active:scale-95 flex items-center justify-center gap-2">
          <span>📊 今すぐExcel(CSV)を出力する</span>
        </a>
      </div>

      <div class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <div class="bg-blue-900 p-4 text-white flex justify-between items-center">
          <div>
            <h1 class="font-black text-base flex items-center gap-1.5">⚙️ でらいど 成約明細台帳</h1>
            <p class="text-[11px] text-blue-200">成約件数: {len(deals)}件 / 手数料率: 10%</p>
          </div>
          <div class="text-right">
            <span class="text-[10px] text-blue-200 block">累計システム手数料</span>
            <span class="text-xl font-black text-yellow-300">¥{total_fee:,}</span>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left min-w-[600px]">
            <tr class="bg-gray-100 border-b border-gray-300 text-[11px] text-gray-600 uppercase">
              <th class="p-3 font-semibold">成約日</th>
              <th class="p-3 font-semibold">成約商品</th>
              <th class="p-3 font-semibold">取引店舗</th>
              <th class="p-3 text-right font-semibold">成約価格(税込)</th>
              <th class="p-3 text-right font-semibold">手数料(10%)</th>
              <th class="p-3 text-right font-semibold">売手受取額</th>
            </tr>
            {rows}
          </table>
        </div>
      </div>
    </div>
    """
    return render_page(content, active_tab="admin")

# --- G. CSVダウンロード処理 ---
def download_csv(handler_obj):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT deals.id, deals.closed_at, items.title, seller.name, buyer.name, deals.deal_price, deals.fee_amount 
                 FROM deals JOIN items ON deals.item_id = items.id 
                 JOIN shops as seller ON deals.seller_shop_id = seller.id 
                 JOIN shops as buyer ON deals.buyer_shop_id = buyer.id ORDER BY deals.closed_at DESC""")
    deals = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['取引ID', '成約日時', '商品名', '出品店舗(売手)', '購入店舗(買手)', '決済額(成約価格)', 'でらいど手数料(10%)', '出品者受取額'])
    for d in deals:
        writer.writerow([d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[5]-d[6]])
        
    csv_data = output.getvalue().encode('shift_jis', errors='replace')
    handler_obj.send_response(200)
    handler_obj.send_header('Content-Type', 'text/csv; charset=Shift_JIS')
    handler_obj.send_header('Content-Disposition', f'attachment; filename="deride_deals_{datetime.now().strftime("%Y%m%d")}.csv"')
    handler_obj.end_headers()
    handler_obj.wfile.write(csv_data)

# ==========================================
# 4. 通信リクエスト処理（Vercelサーバーレス完全対応）
# ==========================================
class handler(http.server.BaseHTTPRequestHandler):
    def send_html(self, html):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
        
    def send_raw(self, content_type, data):
        self.send_response(200)
        self.send_header('Content-type', content_type)
        self.end_headers()
        self.wfile.write(data.encode('utf-8'))
        
    def send_redirect(self, url):
        self.send_response(303)
        self.send_header('Location', url)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # バナー画像ファイルの配信（カレント / apiフォルダ内 / 親フォルダを自動探索）[cite: 1]
        if path == '/banner.jpg':
            candidates = [
                'banner.jpg',
                os.path.join(os.path.dirname(__file__), 'banner.jpg'),
                os.path.join(os.path.dirname(__file__), '..', 'banner.jpg')
            ]
            for p in candidates:
                if os.path.exists(p):
                    try:
                        with open(p, 'rb') as f:
                            self.send_response(200)
                            self.send_header('Content-type', 'image/jpeg')
                            self.end_headers()
                            self.wfile.write(f.read())
                        return
                    except: pass
            self.send_error(404)
            return

        elif path == '/manifest.json': self.send_raw('application/manifest+json; charset=utf-8', MANIFEST_DATA)
        elif path == '/sw.js': self.send_raw('application/javascript; charset=utf-8', SW_JS)
        elif path == '/app-icon.svg': self.send_raw('image/svg+xml; charset=utf-8', APP_ICON_SVG)
            
        elif path in ('', '/', '/index.html'): self.send_html(render_home())
        elif path == '/likes': self.send_html(render_likes())
        elif path == '/sell': self.send_html(render_sell())
        elif path == '/mypage': 
            shop_id = query.get('shop_id', [''])[0]
            self.send_html(render_mypage(shop_id))
        elif path.startswith('/items/') and path.endswith('/edit'):
            item_id = path.split('/')[2]
            self.send_html(render_sell(edit_item_id=item_id))
        elif path.startswith('/items/'): 
            self.send_html(render_detail(path.split('/')[-1]))
        elif path == '/admin/deals': self.send_html(render_admin())
        elif path == '/admin/deals/download': download_csv(self)
        else: self.send_html(render_home())

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8'))
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if self.path == '/items/create':
            c.execute("""
                INSERT INTO items (
                    shop_id, category, title, price, description, status, created_at, image_data,
                    brand, item_condition, shipping_fee, shipping_method, shipping_area, shipping_days, likes_count
                ) VALUES (?, ?, ?, ?, ?, '出品中', ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                data['shop_id'][0], data['category'][0], data['title'][0], data['price'][0], data['description'][0], 
                datetime.now().strftime('%Y-%m-%d %H:%M'), data.get('image_data_json', [''])[0],
                data.get('brand', [''])[0], data.get('item_condition', [''])[0], data.get('shipping_fee', [''])[0], 
                data.get('shipping_method', [''])[0], data.get('shipping_area', [''])[0], data.get('shipping_days', [''])[0]
            ))
            conn.commit()
            self.send_redirect('/')

        elif self.path == '/items/update':
            c.execute("""
                UPDATE items SET 
                    shop_id=?, category=?, title=?, price=?, description=?,
                    brand=?, item_condition=?, shipping_fee=?, shipping_method=?, shipping_area=?, shipping_days=?
                WHERE id=?
            """, (
                data['shop_id'][0], data['category'][0], data['title'][0], data['price'][0], data['description'][0],
                data.get('brand', [''])[0], data.get('item_condition', [''])[0], data.get('shipping_fee', [''])[0], 
                data.get('shipping_method', [''])[0], data.get('shipping_area', [''])[0], data.get('shipping_days', [''])[0],
                data['item_id'][0]
            ))
            conn.commit()
            self.send_redirect(f"/items/{data['item_id'][0]}")

        elif self.path == '/items/like':
            item_id = data['item_id'][0]
            c.execute("UPDATE items SET likes_count = COALESCE(likes_count, 0) + 1 WHERE id = ?", (item_id,))
            conn.commit()
            self.send_redirect(f"/items/{item_id}")

        elif self.path == '/items/delete':
            c.execute("DELETE FROM items WHERE id = ?", (data['item_id'][0],))
            c.execute("DELETE FROM comments WHERE id = ?", (data['item_id'][0],))
            conn.commit()
            self.send_redirect('/')

        elif self.path == '/comments/create':
            c.execute("INSERT INTO comments (item_id, shop_id, message, created_at) VALUES (?, ?, ?, ?)",
                      (data['item_id'][0], data['shop_id'][0], data['message'][0], datetime.now().strftime('%Y-%m-%d %H:%M')))
            conn.commit()
            self.send_redirect(f"/items/{data['item_id'][0]}")

        elif self.path == '/deals/close':
            price = int(data['price'][0])
            fee_10pct = int(price * 0.10)
            c.execute("INSERT INTO deals (item_id, seller_shop_id, buyer_shop_id, deal_price, fee_amount, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (data['item_id'][0], data['seller_shop_id'][0], data['buyer_shop_id'][0], price, fee_10pct, datetime.now().strftime('%Y-%m-%d %H:%M')))
            c.execute("UPDATE items SET status = '成約済み' WHERE id = ?", (data['item_id'][0],))
            conn.commit()
            self.send_redirect(f"/items/{data['item_id'][0]}")

        conn.close()

Handler = handler

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", port), handler) as httpd:
        print(f"★ 起動中 PORT: {port}")
        httpd.serve_forever()
