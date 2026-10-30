import http.server
import socketserver
import sqlite3
import urllib.parse
import json
import csv
import io
import os
import tempfile
import traceback
from datetime import datetime

# ==========================================
# 0. データベース保存先
# ==========================================
DB_PATH = os.path.join(tempfile.gettempdir(), 'deride_platform.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# 1. CSV店舗マスター読み込みと初期化
# ==========================================
def load_shops_from_csv():
    shops = []
    csv_paths = [
        'shops.csv',
        os.path.join(os.path.dirname(__file__), 'shops.csv'),
        os.path.join(os.path.dirname(__file__), '..', 'shops.csv')
    ]
    target_csv = None
    for p in csv_paths:
        if os.path.exists(p):
            target_csv = p
            break

    if target_csv:
        for enc in ['utf-8-sig', 'shift_jis', 'cp932', 'utf-8']:
            try:
                with open(target_csv, 'r', encoding=enc) as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    for idx, row in enumerate(reader, 1):
                        if not row or len(row) < 2: continue
                        s_id = row[0].strip() if len(row) > 0 and row[0].strip().isdigit() else idx
                        pref = row[1].strip() if len(row) > 1 else "愛知県"
                        district = row[2].strip() if len(row) > 2 else ""
                        branch = row[3].strip() if len(row) > 3 else ""
                        group = row[4].strip() if len(row) > 4 else ""
                        name = row[5].strip() if len(row) > 5 else (row[1].strip() if len(row) > 1 else f"専売店{idx}")
                        shops.append((int(s_id), pref, district, branch, group, name))
                if shops:
                    break
            except Exception:
                continue

    if not shops:
        shops = [
            (1, '愛知県', '名古屋市', '名古屋中支部', '栄班', '中日新聞 栄専売店'),
            (2, '愛知県', '名古屋市', '名古屋北支部', '名北班', '中日新聞 名北専売店'),
            (3, '愛知県', '尾張地区', '一宮支部', '一宮班', '中日新聞 一宮専売店'),
            (4, '岐阜県', '岐阜地区', '岐阜南支部', '岐阜南班', '中日新聞 岐阜南専売店'),
            (5, '三重県', '三重地区', '津支部', '津班', '中日新聞 津専売店')
        ]
    return shops

def init_db():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, category TEXT, title TEXT, price INTEGER, 
            status TEXT, description TEXT, created_at TEXT, image_data TEXT,
            brand TEXT, item_condition TEXT, shipping_fee TEXT, shipping_method TEXT, shipping_area TEXT, shipping_days TEXT,
            likes_count INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, seller_shop_id INTEGER, buyer_shop_id INTEGER, 
            deal_price INTEGER, fee_amount INTEGER, closed_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, shop_id INTEGER, message TEXT, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY, pref TEXT, district TEXT, branch TEXT, group_name TEXT, name TEXT
        )""")
        
        c.execute("DELETE FROM shops")
        shop_data = load_shops_from_csv()
        c.executemany("INSERT OR REPLACE INTO shops VALUES (?, ?, ?, ?, ?, ?)", shop_data)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB初期化エラー: {e}")

init_db()

# ==========================================
# 2. PWA設定データ
# ==========================================
APP_ICON_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%231e40af'/><text x='50%' y='48%' font-size='42' text-anchor='middle' dominant-baseline='central'>🏍️</text><text x='50%' y='80%' font-size='15' font-weight='bold' fill='white' text-anchor='middle'>公式 でらイド</text></svg>"""

MANIFEST_DATA = json.dumps({
    "name": "中日新聞 バイクマーケット 公式 でらイド",
    "short_name": "公式 でらイド",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#1e40af",
    "theme_color": "#1e40af",
    "icons": [{"src": "/app-icon.svg", "sizes": "192x192 512x512", "type": "image/svg+xml"}]
}, ensure_ascii=False)

SW_JS = "self.addEventListener('install', e => self.skipWaiting()); self.addEventListener('activate', e => self.clients.claim()); self.addEventListener('fetch', e => e.respondWith(fetch(e.request).catch(() => caches.match(e.request))));"

# ==========================================
# 3. 共通レイアウト
# ==========================================
BASE_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>公式 でらイド - 中日新聞専売店 バイクマーケット</title>
  <link rel="manifest" href="/manifest.json">
  <link rel="apple-touch-icon" href="/app-icon.svg">
  <link rel="icon" type="image/svg+xml" href="/app-icon.svg">
  <meta name="theme-color" content="#1e40af">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 text-gray-800 pb-28 select-none">
  <header class="bg-blue-800 text-white sticky top-0 z-40 shadow pt-[env(safe-area-inset-top)]">
    <div class="max-w-4xl mx-auto px-4 py-2.5 flex justify-between items-center">
      <a href="/?mode=__MODE__" class="font-bold text-base md:text-lg tracking-wide flex items-center gap-1.5">
        <span class="bg-yellow-400 text-blue-900 text-[10px] px-1.5 py-0.5 rounded font-black">公式</span>
        <span>でらイド</span>
      </a>
      <div class="flex items-center gap-2">
        <div class="bg-blue-950 p-0.5 rounded-lg border border-blue-700 flex text-xs">
          <a href="/?mode=buyer" class="px-2.5 py-1 rounded-md font-bold transition __BUYER_MODE_CLS__">🛒 購入者</a>
          <a href="/?mode=seller" class="px-2.5 py-1 rounded-md font-bold transition __SELLER_MODE_CLS__">📦 出品者</a>
        </div>
        <a href="/admin/deals?mode=__MODE__" class="text-xs bg-yellow-400 text-blue-950 font-bold px-2 py-1.5 rounded-lg shadow hover:bg-yellow-300 transition">📊 Excel</a>
      </div>
    </div>
  </header>
  <main class="max-w-4xl mx-auto p-4">__CONTENT__</main>
  <nav class="fixed bottom-0 left-0 right-0 z-50 bg-white/95 backdrop-blur border-t border-gray-200 shadow pb-[env(safe-area-inset-bottom)]">
    <div class="max-w-md mx-auto grid grid-cols-5 h-16">
      <a href="/?mode=__MODE__" class="flex flex-col items-center justify-center text-xs transition __HOME_CLS__ active:scale-95"><span class="text-lg leading-none">🏠</span><span class="mt-1 text-[9px]">ホーム</span></a>
      <a href="/likes?mode=__MODE__" class="flex flex-col items-center justify-center text-xs transition __LIKES_CLS__ active:scale-95"><span class="text-lg leading-none">❤️</span><span class="mt-1 text-[9px]">いいね</span></a>
      <a href="/sell?mode=__MODE__" class="flex flex-col items-center justify-center text-xs transition __SELL_CLS__ active:scale-95"><span class="text-lg leading-none">📷</span><span class="mt-1 text-[9px]">出品</span></a>
      <a href="/mypage?mode=__MODE__" class="flex flex-col items-center justify-center text-xs transition __MYPAGE_CLS__ active:scale-95"><span class="text-lg leading-none">👤</span><span class="mt-1 text-[9px]">マイページ</span></a>
      <a href="/admin/deals?mode=__MODE__" class="flex flex-col items-center justify-center text-xs transition __ADMIN_CLS__ active:scale-95"><span class="text-lg leading-none">📊</span><span class="mt-1 text-[9px]">管理台帳</span></a>
    </div>
  </nav>
</body>
</html>"""

def render_page(content, active_tab="home", mode="buyer"):
    inactive_cls = "text-gray-400 hover:text-gray-600 font-medium"
    active_cls = "text-blue-600 font-bold"
    buyer_btn_cls = "bg-emerald-600 text-white" if mode == "buyer" else "text-blue-200 hover:text-white"
    seller_btn_cls = "bg-blue-600 text-white" if mode == "seller" else "text-blue-200 hover:text-white"

    html = BASE_HTML.replace("__CONTENT__", content)
    html = html.replace("__HOME_CLS__", active_cls if active_tab == "home" else inactive_cls)
    html = html.replace("__LIKES_CLS__", active_cls if active_tab == "likes" else inactive_cls)
    html = html.replace("__SELL_CLS__", active_cls if active_tab == "sell" else inactive_cls)
    html = html.replace("__MYPAGE_CLS__", active_cls if active_tab == "mypage" else inactive_cls)
    html = html.replace("__ADMIN_CLS__", active_cls if active_tab == "admin" else inactive_cls)
    html = html.replace("__MODE__", mode)
    html = html.replace("__BUYER_MODE_CLS__", buyer_btn_cls)
    html = html.replace("__SELLER_MODE_CLS__", seller_btn_cls)
    return html

def build_item_cards(items, mode="buyer"):
    items_html = ""
    for item in items:
        color = "bg-green-100 text-green-800" if item['category'] == "バイク" else "bg-orange-100 text-orange-800"
        img_src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' viewBox='0 0 24 24' fill='none' stroke='%23ccc' stroke-width='1'><rect width='18' height='18' x='3' y='3' rx='2'/><circle cx='8.5' cy='8.5' r='1.5'/></svg>"
        raw_img = item['image_data']
        img_count_badge = ""
        if raw_img:
            if raw_img.startswith('['):
                try:
                    imgs = json.loads(raw_img)
                    if imgs and len(imgs) > 0: 
                        img_src = imgs[0]
                        img_count_badge = f'<span class="absolute bottom-1 right-1 bg-black/60 text-white text-[9px] px-1.5 py-0.5 rounded-md font-bold">📷 {len(imgs)}</span>'
                except: pass
            else:
                img_src = raw_img
        
        status_badge = '<div class="absolute inset-0 bg-black/50 flex items-center justify-center"><span class="bg-red-600 text-white font-bold text-sm px-3 py-1 rounded">成約済み</span></div>' if item['status'] == "成約済み" else ""
        shop_display_name = item['name'] if item['status'] == "成約済み" else "🔒 出品店（成約後開示）"
        likes_val = item['likes_count'] or 0
        likes_display = f'<span class="text-xs text-pink-600 font-semibold flex items-center gap-0.5">❤️ {likes_val}</span>' if likes_val > 0 else ""
        
        btn_label = "購入へ" if mode == "buyer" else "確認・管理"
        btn_bg = "bg-emerald-600 hover:bg-emerald-700" if mode == "buyer" else "bg-blue-600 hover:bg-blue-700"

        items_html += f"""
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col justify-between hover:shadow-md transition">
          <div class="w-full h-40 bg-gray-100 flex items-center justify-center overflow-hidden relative">
            <img src="{img_src}" alt="{item['title']}" class="w-full h-full object-cover">
            {img_count_badge}
            {status_badge}
          </div>
          <div class="p-3 flex-1 flex flex-col justify-between">
            <div>
              <div class="flex items-center justify-between mb-1">
                <span class="text-[11px] px-2 py-0.5 rounded font-semibold {color}">{item['category']}</span>
                <span class="text-[11px] text-gray-400">{str(item['created_at'])[:10]}</span>
              </div>
              <h3 class="font-bold text-gray-900 text-sm line-clamp-1 h-5">{item['title']}</h3>
              <p class="text-xs text-gray-500 mt-1 line-clamp-1">{item['pref']} {item['branch']}</p>
              <p class="text-xs font-semibold text-gray-700 line-clamp-1">{shop_display_name}</p>
            </div>
            
            <div class="mt-3 pt-2 border-t flex items-center justify-between min-h-[38px]">
              <div class="flex-1 mr-1">
                <span class="text-base font-black text-red-600 truncate block">¥{item['price']:,}</span>
              </div>
              <div class="flex items-center gap-1.5 flex-shrink-0">
                {likes_display}
                <a href="/items/{item['id']}?mode={mode}" class="{btn_bg} text-white text-xs font-bold px-2.5 py-1.5 rounded-lg shadow-sm active:scale-95 transition text-center whitespace-nowrap block">
                  {btn_label}
                </a>
              </div>
            </div>
          </div>
        </div>
        """
    return items_html

# --- A. ホーム画面 ---
def render_home(mode="buyer"):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT i.*, s.name, s.pref, s.branch
        FROM items i JOIN shops s ON i.shop_id = s.id 
        ORDER BY i.id DESC
    """)
    items = c.fetchall()
    conn.close()

    items_html = build_item_cards(items, mode=mode) or '<div class="col-span-full text-center py-16 bg-white rounded-xl border border-dashed border-gray-300 text-gray-400"><p class="text-sm font-bold">出品中の車両・部品はありません。</p></div>'

    if mode == "seller":
        action_btn = '<a href="/sell?mode=seller" class="bg-blue-600 text-white font-bold text-xs px-3.5 py-1.5 rounded-xl shadow hover:bg-blue-700 transition flex items-center gap-1"><span>📷</span> 出品する</a>'
        mode_badge = '<span class="bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded-full font-bold">出品者モード</span>'
    else:
        action_btn = '<div class="bg-emerald-50 text-emerald-800 font-bold text-xs px-3 py-1.5 rounded-xl border border-emerald-200 flex items-center gap-1"><span>🛒</span> 車両購入受付中</div>'
        mode_badge = '<span class="bg-emerald-100 text-emerald-800 text-xs px-2 py-0.5 rounded-full font-bold">購入者モード</span>'

    content = f"""
    <div class="rounded-2xl overflow-hidden shadow-md mb-4 border border-blue-200 bg-blue-50">
      <img src="/banner.jpg" alt="公式 でらイド 新聞販売店専用アプリ" class="w-full h-auto object-cover block">
    </div>
    <div class="flex items-center justify-between mb-3 bg-white p-3 rounded-xl border shadow-sm">
      <div class="flex items-center gap-2">
        <h2 class="text-sm md:text-base font-bold text-gray-900 flex items-center gap-1"><span>🏍️</span><span>在庫一覧</span><span class="text-xs font-normal text-gray-500">({len(items)}件)</span></h2>
        {mode_badge}
      </div>
      {action_btn}
    </div>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">{items_html}</div>
    """
    return render_page(content, active_tab="home", mode=mode)

# --- B. いいね画面 ---
def render_likes(mode="buyer"):
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT i.*, s.name, s.pref, s.branch FROM items i JOIN shops s ON i.shop_id = s.id WHERE COALESCE(i.likes_count, 0) > 0 ORDER BY i.likes_count DESC, i.id DESC""")
    items = c.fetchall()
    conn.close()

    items_html = build_item_cards(items, mode=mode) or f'<div class="col-span-full text-center py-16 bg-white rounded-xl border border-dashed border-pink-200 text-gray-400"><span class="text-4xl block mb-2">❤️</span><p class="text-sm font-bold text-gray-700">まだ「いいね」された商品はありません</p><a href="/?mode={mode}" class="inline-block mt-4 px-4 py-2 bg-blue-600 text-white font-bold text-xs rounded-lg shadow hover:bg-blue-700">商品を探しにいく</a></div>'
    content = f'<div class="mb-4"><h2 class="text-base font-bold text-gray-900 flex items-center gap-1.5"><span class="text-pink-600 text-lg">❤️</span><span>いいね！された人気商品</span><span class="text-xs font-normal text-gray-500">({len(items)}件)</span></h2></div><div class="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">{items_html}</div>'
    return render_page(content, active_tab="likes", mode=mode)

# --- C. 出品画面（画像軽量化・プレビュー完全実装版） ---
def render_sell(edit_item_id=None, mode="seller"):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, pref, district, branch, group_name, name FROM shops ORDER BY pref, district, branch, group_name, name")
    raw_shops = c.fetchall()
    shops_data = [{"id": r['id'], "p": r['pref'] or "", "d": r['district'] or "", "b": r['branch'] or "", "g": r['group_name'] or "", "n": r['name'] or ""} for r in raw_shops]
    shops_json = json.dumps(shops_data, ensure_ascii=False)

    item_to_edit = None
    if edit_item_id:
        c.execute("SELECT * FROM items WHERE id=?", (edit_item_id,))
        item_to_edit = c.fetchone()
    conn.close()

    is_edit = item_to_edit is not None
    form_action = f"/items/update?mode={mode}" if is_edit else f"/items/create?mode={mode}"
    page_title = "✏️ 出品情報を編集する" if is_edit else "📷 でらイド に出品する"

    item_id_val = item_to_edit['id'] if is_edit else ""
    title_val = item_to_edit['title'] if is_edit else ""
    price_val = item_to_edit['price'] if is_edit else ""
    desc_val = item_to_edit['description'] if is_edit else ""
    cat_val = item_to_edit['category'] if is_edit else "バイク"
    brand_val = item_to_edit['brand'] if is_edit else "ホンダ"
    img_json_val = item_to_edit['image_data'] if is_edit and item_to_edit['image_data'] else ""

    template = f"""
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-4 md:p-6 mb-6">
      <div class="border-b pb-3 mb-4 flex justify-between items-center">
        <h1 class="text-base md:text-lg font-black text-gray-900"><span>{page_title}</span></h1>
        <span class="bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded font-bold">出品者モード</span>
      </div>

      <form action="{form_action}" method="post" class="space-y-4" id="sellForm">
        <input type="hidden" name="item_id" value="{item_id_val}">
        
        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block text-xs font-bold text-gray-700">写真を追加（最大10枚）</label>
            <span id="imgCounter" class="text-xs text-blue-600 font-bold">0 / 10枚</span>
          </div>
          <input type="file" id="filePicker" accept="image/*" multiple class="block w-full text-xs text-gray-500 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-blue-100 file:text-blue-700 font-bold cursor-pointer">
          <input type="hidden" name="image_data_json" id="imageDataField" value='{img_json_val}'>
          <div id="imagePreviewContainer" class="mt-2.5 hidden flex flex-wrap gap-2 p-2.5 bg-gray-50 rounded-xl border border-dashed border-gray-300"></div>
        </div>

        <div class="bg-blue-50/70 p-3 rounded-xl border border-blue-200 space-y-2">
          <label class="block text-xs font-bold text-blue-900">出品店舗を選択（CSVリストより反映）</label>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div><label class="block text-[10px] text-gray-600 mb-0.5">① 県</label><select id="treePref" class="w-full border rounded-lg p-2 text-xs bg-white"></select></div>
            <div id="districtBox"><label class="block text-[10px] text-gray-600 mb-0.5">② 地区</label><select id="treeDistrict" class="w-full border rounded-lg p-2 text-xs bg-white"></select></div>
            <div><label class="block text-[10px] text-gray-600 mb-0.5">③ 支部</label><select id="treeBranch" class="w-full border rounded-lg p-2 text-xs bg-white"></select></div>
            <div id="groupBox"><label class="block text-[10px] text-gray-600 mb-0.5">④ 班</label><select id="treeGroup" class="w-full border rounded-lg p-2 text-xs bg-white"></select></div>
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
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-700 mb-1">商品タイトル</label>
          <input type="text" name="title" value="{title_val}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="例: スーパーカブ50プロ 配達ボックス付き" required>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-700 mb-1">希望価格 (円)</label>
          <input type="number" name="price" id="inputPrice" value="{price_val}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="例: 85000" required>
          <div id="feeEstimation" class="mt-2 p-2.5 bg-gray-50 rounded-lg border border-gray-200 text-xs space-y-1">
            <div class="flex justify-between text-gray-600"><span>手数料 (10%):</span><span id="estFee" class="text-red-600 font-bold">¥0</span></div>
            <div class="flex justify-between text-green-700 font-bold border-t pt-1"><span>手取受取額:</span><span id="estNet" class="text-sm">¥0</span></div>
          </div>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-700 mb-1">車両状態・備考</label>
          <textarea name="description" class="w-full border rounded-lg p-2 text-sm h-24" required>{desc_val}</textarea>
        </div>

        <button type="submit" id="submitBtn" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl text-sm shadow-md transition active:scale-95">
          {"更新内容を保存する" if is_edit else "でらイドに出品登録する"}
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

      // 価格手数料計算
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

      // 写真自動リサイズ＆圧縮登録処理（スマホ大容量画像完全対応）
      const filePicker = document.getElementById('filePicker');
      const imgField = document.getElementById('imageDataField');
      const imgPreview = document.getElementById('imagePreviewContainer');
      const imgCounter = document.getElementById('imgCounter');

      // 編集時の既存画像プレビュー復元
      if (imgField.value) {{
        try {{
          const existImgs = JSON.parse(imgField.value);
          if (Array.isArray(existImgs) && existImgs.length > 0) {{
            imgPreview.classList.remove('hidden');
            imgCounter.innerText = `${{existImgs.length}} / 10枚`;
            existImgs.forEach(src => {{
              const d = document.createElement('div');
              d.className = 'w-16 h-16 rounded-lg border overflow-hidden shadow-sm bg-black/10';
              d.innerHTML = `<img src="${{src}}" class="w-full h-full object-cover">`;
              imgPreview.appendChild(d);
            }});
          }}
        }} catch(e) {{}}
      }}

      filePicker.addEventListener('change', function(e) {{
        const files = e.target.files;
        if (!files || files.length === 0) return;
        const total = Math.min(files.length, 10);
        
        imgPreview.innerHTML = '<div class="text-xs text-blue-600 font-bold p-2 w-full animate-pulse">📷 スマホ写真を高画質圧縮中...</div>';
        imgPreview.classList.remove('hidden');
        imgCounter.innerText = `処理中 (0 / ${{total}}枚)`;
        
        const compressedList = new Array(total);
        let doneCount = 0;

        for (let i = 0; i < total; i++) {{
          const reader = new FileReader();
          reader.onload = function(evt) {{
            const img = new Image();
            img.onload = function() {{
              const canvas = document.createElement('canvas');
              let width = img.width;
              let height = img.height;
              const maxSide = 960; // 画面表示に最適・サーバー送信も軽快なサイズ

              if (width > height && width > maxSide) {{
                height = Math.round((height * maxSide) / width);
                width = maxSide;
              }} else if (height > maxSide) {{
                width = Math.round((width * maxSide) / height);
                height = maxSide;
              }}

              canvas.width = width;
              canvas.height = height;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(img, 0, 0, width, height);

              // JPEG形式で品質0.7（超軽量・綺麗）
              compressedList[i] = canvas.toDataURL('image/jpeg', 0.70);
              doneCount++;
              imgCounter.innerText = `圧縮中 (${{doneCount}} / ${{total}}枚)`;

              if (doneCount === total) {{
                imgField.value = JSON.stringify(compressedList);
                imgCounter.innerText = `${{total}} / 10枚 (完了)`;
                imgPreview.innerHTML = '';
                compressedList.forEach(src => {{
                  const thumb = document.createElement('div');
                  thumb.className = 'w-16 h-16 rounded-lg border overflow-hidden shadow-sm bg-black/10 flex-shrink-0';
                  thumb.innerHTML = `<img src="${{src}}" class="w-full h-full object-cover">`;
                  imgPreview.appendChild(thumb);
                }});
              }}
            }};
            img.src = evt.target.result;
          }};
          reader.readAsDataURL(files[i]);
        }}
      }});
    </script>
    """
    content = template.replace("__SHOPS_JSON__", shops_json)
    return render_page(content, active_tab="sell", mode=mode)

# --- D. 商品詳細画面 ---
def render_detail(item_id, mode="buyer"):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT i.*, s.name, s.pref, s.branch, s.district, s.group_name
        FROM items i JOIN shops s ON i.shop_id = s.id 
        WHERE i.id=?
    """, (item_id,))
    item = c.fetchone()
    
    c.execute("SELECT comments.message, comments.created_at, shops.name FROM comments JOIN shops ON comments.shop_id = shops.id WHERE comments.item_id=? ORDER BY comments.id ASC", (item_id,))
    comments = c.fetchall()
    
    c.execute("SELECT id, pref, district, branch, group_name, name FROM shops ORDER BY pref, district, branch, group_name, name")
    raw_shops = c.fetchall()
    shops_data = [{"id": r['id'], "p": r['pref'] or "", "d": r['district'] or "", "b": r['branch'] or "", "g": r['group_name'] or "", "n": r['name'] or ""} for r in raw_shops]
    shops_json = json.dumps(shops_data, ensure_ascii=False)
    
    commenter_options = "".join([f'<option value="{s["id"]}">[{s["pref"]} {s["branch"]}] {s["name"]}</option>' for s in raw_shops])
    conn.close()

    if not item: return render_page("<p class='p-8 text-center'>商品が見つかりません。<br><a href='/' class='text-blue-600 font-bold underline mt-2 inline-block'>トップに戻る</a></p>", active_tab="home", mode=mode)
    
    price = item['price']
    likes_count = item['likes_count'] or 0
    is_closed = item['status'] == "成約済み"

    seller_name_display = item['name'] if is_closed else "🔒 出品店（成約後開示）"

    raw_img = item['image_data']
    images = []
    if raw_img:
        if raw_img.startswith('['):
            try: images = json.loads(raw_img)
            except: pass
        else:
            images = [raw_img]

    img_html = ""
    if images and len(images) > 0:
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
        is_seller = com['name'] == item['name']
        badge = '<span class="ml-1 text-[10px] bg-blue-600 text-white px-1 py-0.5 rounded">出品店</span>' if is_seller else ''
        bg_cls = 'bg-blue-50 border-blue-200' if is_seller else 'bg-gray-50 border-gray-200'
        sender_disp = com['name'] if (is_closed or is_seller) else "質問店舗"
        comments_html += f"""
        <div class="{bg_cls} p-2.5 rounded-lg border mb-2 text-xs">
          <div class="flex justify-between items-center mb-1 font-bold text-gray-700">
            <span>{sender_disp} {badge}</span>
            <span class="text-[10px] text-gray-400 font-normal">{str(com['created_at'])[:16]}</span>
          </div>
          <p class="text-gray-800 whitespace-pre-wrap">{com['message']}</p>
        </div>"""

    # 購入者モード時の購入フォーム
    buyer_purchase_area = ""
    if mode == "buyer":
        if not is_closed:
            buyer_purchase_area = f"""
            <div class="bg-emerald-50 border border-emerald-300 rounded-xl p-4 space-y-3 mt-4 shadow-sm">
              <h4 class="font-bold text-sm text-emerald-950 flex items-center gap-1.5">
                <span>🛒</span> この車両・部品を購入する
              </h4>
              <p class="text-xs text-emerald-700">購入するあなたの店舗を選択してください。成約後に出品店舗の詳細情報が開示されます。</p>
              
              <form action="/deals/close?mode={mode}" method="post" class="space-y-3 pt-1">
                <input type="hidden" name="item_id" value="{item['id']}">
                <input type="hidden" name="seller_shop_id" value="{item['shop_id']}">
                <input type="hidden" name="price" value="{item['price']}">

                <div class="bg-white p-3 rounded-xl border border-emerald-200 space-y-2">
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div>
                      <label class="block text-[10px] text-gray-600 mb-0.5">① 県</label>
                      <select id="buyerTreePref" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
                    </div>
                    <div id="buyerDistrictBox">
                      <label class="block text-[10px] text-gray-600 mb-0.5">② 地区</label>
                      <select id="buyerTreeDistrict" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
                    </div>
                    <div>
                      <label class="block text-[10px] text-gray-600 mb-0.5">③ 支部</label>
                      <select id="buyerTreeBranch" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
                    </div>
                    <div id="buyerGroupBox">
                      <label class="block text-[10px] text-gray-600 mb-0.5">④ 班</label>
                      <select id="buyerTreeGroup" class="w-full border rounded-lg p-2 text-xs bg-white"></select>
                    </div>
                  </div>
                  <div>
                    <label class="block text-[10px] text-gray-600 mb-0.5 font-bold">⑤ 自店舗名</label>
                    <select id="buyerTreeShop" name="buyer_shop_id" class="w-full border rounded-lg p-2.5 text-xs font-bold bg-white text-emerald-900" required>
                      <option value="">↑ 上の県・支部を選択してください</option>
                    </select>
                  </div>
                </div>

                <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-lg text-sm shadow transition active:scale-95">
                  ¥{item['price']:,} で購入・成約確定
                </button>
              </form>
            </div>
            """
        else:
            buyer_purchase_area = '<div class="bg-gray-100 border border-gray-300 rounded-xl p-3.5 text-center text-xs text-gray-500 font-bold mt-4">この商品はすでに成約済みです。</div>'

    seller_admin_menu = ""
    if mode == "seller":
        fee_10pct = int(price * 0.10)
        net_income = price - fee_10pct
        seller_admin_menu = f"""
        <details class="bg-blue-50/60 border border-blue-200 rounded-xl overflow-hidden text-xs text-gray-700 mt-4">
          <summary class="p-3.5 font-bold cursor-pointer flex items-center justify-between bg-blue-100/70 hover:bg-blue-200 text-blue-950">
            <span>⚙️ 出品店舗専用メニュー（修正・削除）</span><span class="text-[10px] text-blue-600">開く ▼</span>
          </summary>
          <div class="p-4 space-y-3 bg-white border-t">
            <div class="bg-gray-50 p-2.5 rounded border space-y-1">
              <div class="flex justify-between"><span>売値:</span><span class="font-bold">¥{price:,}</span></div>
              <div class="flex justify-between text-red-600"><span>手数料(10%):</span><span>-¥{fee_10pct:,}</span></div>
              <div class="border-t pt-1 flex justify-between font-black text-emerald-700"><span>手取受取額:</span><span>¥{net_income:,}</span></div>
            </div>
            <div class="flex gap-2">
              <a href="/items/{item['id']}/edit?mode={mode}" class="flex-1 text-center bg-amber-500 hover:bg-amber-600 text-white font-bold py-2 rounded-lg shadow text-xs">✏️ 出品内容を編集する</a>
              <form action="/items/delete?mode={mode}" method="post" onsubmit="return confirm('本当に削除しますか？');" class="flex-shrink-0">
                <input type="hidden" name="item_id" value="{item['id']}">
                <button type="submit" class="text-xs text-red-600 border border-red-300 rounded-lg px-3 py-2 hover:bg-red-50 font-bold">🗑️ 削除</button>
              </form>
            </div>
          </div>
        </details>
        """

    status_tag = f'<span class="text-xs px-2.5 py-0.5 rounded-full font-bold bg-red-600 text-white">成約済み</span>' if is_closed else '<span class="text-xs px-2.5 py-0.5 rounded-full font-bold bg-green-600 text-white">出品中</span>'

    content = f"""
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <a href="/?mode={mode}" class="text-xs text-blue-600 font-bold hover:underline">← 一覧に戻る</a>
        <span class="text-xs text-gray-400">ID: #{item['id']}</span>
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        {img_html}
        <div class="flex items-center justify-between"><span class="text-xs px-2 py-0.5 rounded font-bold bg-gray-100 text-gray-700">{item['category']}</span>{status_tag}</div>
        <h1 class="text-xl font-black mt-2 text-gray-900">{item['title']}</h1>
        <div class="mt-3 pt-3 border-t flex items-center justify-between">
          <div><span class="text-xs text-gray-500 block">販売価格（税込）</span><span class="text-2xl font-black text-red-600">¥{item['price']:,}</span></div>
          <form action="/items/like?mode={mode}" method="post" class="inline">
            <input type="hidden" name="item_id" value="{item['id']}">
            <button type="submit" class="flex items-center gap-1.5 px-4 py-2 rounded-full border border-pink-200 bg-pink-50 text-pink-600 font-bold text-xs shadow-sm">
              <span>❤️ いいね！</span><span class="bg-white px-2 py-0.5 rounded-full font-black border text-xs">{likes_count}</span>
            </button>
          </form>
        </div>
        <div class="mt-4 pt-3 border-t text-xs space-y-1.5 text-gray-600">
          <p><strong class="text-gray-800">出品地域:</strong> {item['pref']} {item['branch']}</p>
          <p><strong class="text-gray-800">出品店舗:</strong> <span class="font-bold text-blue-900">{seller_name_display}</span></p>
          <p><strong class="text-gray-800">登録日:</strong> {str(item['created_at'])[:10]}</p>
          <div class="bg-gray-50 p-3 rounded-lg border mt-2 whitespace-pre-wrap text-sm text-gray-800 leading-relaxed">{item['description']}</div>
        </div>
        {buyer_purchase_area}
      </div>
      <div class="bg-white rounded-xl shadow-sm border p-4">
        <h3 class="font-bold text-sm mb-1 text-blue-900">💬 質問・商談メッセージ</h3>
        <div class="max-h-64 overflow-y-auto mb-3">{comments_html or '<p class="text-xs text-gray-400 text-center py-2">質問はありません</p>'}</div>
        <form action="/comments/create?mode={mode}" method="post" class="space-y-2 pt-2 border-t">
          <input type="hidden" name="item_id" value="{item['id']}">
          <select name="shop_id" class="w-full border rounded-lg p-2 text-xs bg-white">{commenter_options}</select>
          <textarea name="message" placeholder="質問・商談内容を入力..." class="w-full border rounded-lg p-2 text-xs h-16" required></textarea>
          <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded-lg text-xs hover:bg-blue-700 shadow">コメント送信</button>
        </form>
      </div>
      {seller_admin_menu}
    </div>

    <!-- 購入者用自店舗選択ツリー連動スクリプト -->
    <script>
      const buyerShops = __SHOPS_JSON__;
      const currentSellerShopId = {item['shop_id']};
      const selectableShops = buyerShops.filter(s => s.id !== currentSellerShopId);

      const bPrefEl = document.getElementById('buyerTreePref');
      const bDistEl = document.getElementById('buyerTreeDistrict');
      const bDistBox = document.getElementById('buyerDistrictBox');
      const bBranchEl = document.getElementById('buyerTreeBranch');
      const bGroupEl = document.getElementById('buyerTreeGroup');
      const bGroupBox = document.getElementById('buyerGroupBox');
      const bShopEl = document.getElementById('buyerTreeShop');

      if (bPrefEl) {{
        const bPrefs = [...new Set(selectableShops.map(s => s.p).filter(Boolean))];
        bPrefEl.innerHTML = '<option value="">県を選択</option>' + bPrefs.map(p => '<option value="' + p + '">' + p + '</option>').join('');

        bPrefEl.addEventListener('change', () => {{
          const selPref = bPrefEl.value;
          bDistEl.innerHTML = '<option value="">地区を選択</option>';
          bBranchEl.innerHTML = '<option value="">支部を選択</option>';
          bGroupEl.innerHTML = '<option value="">班を選択</option>';
          bShopEl.innerHTML = '<option value="">店舗を選択</option>';
          if (!selPref) return;

          const filtered = selectableShops.filter(s => s.p === selPref);
          const dists = [...new Set(filtered.map(s => s.d).filter(Boolean))];
          if (dists.length === 0) {{
            bDistBox.classList.add('hidden');
            loadBuyerBranches(selPref, "");
          }} else {{
            bDistBox.classList.remove('hidden');
            bDistEl.innerHTML = '<option value="">地区を選択</option>' + dists.map(d => '<option value="' + d + '">' + d + '</option>').join('');
          }}
        }});

        bDistEl.addEventListener('change', () => loadBuyerBranches(bPrefEl.value, bDistEl.value));

        function loadBuyerBranches(pref, dist) {{
          bBranchEl.innerHTML = '<option value="">支部を選択</option>';
          bGroupEl.innerHTML = '<option value="">班を選択</option>';
          bShopEl.innerHTML = '<option value="">店舗を選択</option>';
          const filtered = selectableShops.filter(s => s.p === pref && (!dist || s.d === dist));
          const branches = [...new Set(filtered.map(s => s.b).filter(Boolean))];
          bBranchEl.innerHTML = '<option value="">支部を選択</option>' + branches.map(b => '<option value="' + b + '">' + b + '</option>').join('');
        }}

        bBranchEl.addEventListener('change', () => {{
          const selBranch = bBranchEl.value;
          bGroupEl.innerHTML = '<option value="">班を選択</option>';
          bShopEl.innerHTML = '<option value="">店舗を選択</option>';
          if (!selBranch) return;

          const filtered = selectableShops.filter(s => s.p === bPrefEl.value && (!bDistEl.value || s.d === bDistEl.value) && s.b === selBranch);
          const groups = [...new Set(filtered.map(s => s.g).filter(Boolean))];
          if (groups.length === 0) {{
            bGroupBox.classList.add('hidden');
            loadBuyerShops(bPrefEl.value, bDistEl.value, selBranch, "");
          }} else {{
            bGroupBox.classList.remove('hidden');
            bGroupEl.innerHTML = '<option value="">班を選択</option>' + groups.map(g => '<option value="' + g + '">' + g + '</option>').join('');
          }}
        }});

        bGroupEl.addEventListener('change', () => loadBuyerShops(bPrefEl.value, bDistEl.value, bBranchEl.value, bGroupEl.value));

        function loadBuyerShops(pref, dist, branch, group) {{
          const filtered = selectableShops.filter(s => s.p === pref && (!dist || s.d === dist) && s.b === branch && (!group || s.g === group));
          bShopEl.innerHTML = '<option value="">店舗を選択してください</option>' + filtered.map(s => '<option value="' + s.id + '">' + s.n + '</option>').join('');
        }}
      }}
    </script>
    """
    content = content.replace("__SHOPS_JSON__", shops_json)
    return render_page(content, active_tab="home", mode=mode)

# --- E. マイページ ---
def render_mypage(selected_shop_id=None, mode="buyer"):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, pref, branch, name FROM shops ORDER BY pref, branch, name")
    all_shops = c.fetchall()

    shop_options = "".join([
        f'<option value="{s["id"]}" {"selected" if selected_shop_id and str(selected_shop_id)==str(s["id"]) else ""}>[{s["pref"]} {s["branch"]}] {s["name"]}</option>'
        for s in all_shops
    ])

    sell_deals_html = ""
    buy_deals_html = ""

    if selected_shop_id:
        c.execute("""
            SELECT d.id, d.closed_at, i.title, b.name, d.deal_price, d.fee_amount, i.id as item_id
            FROM deals d JOIN items i ON d.item_id = i.id JOIN shops b ON d.buyer_shop_id = b.id
            WHERE d.seller_shop_id = ? ORDER BY d.closed_at DESC
        """, (selected_shop_id,))
        for d in c.fetchall():
            net = d['deal_price'] - d['fee_amount']
            sell_deals_html += f"""
            <div class="bg-white border rounded-xl p-3 shadow-sm flex flex-col justify-between">
              <div class="flex justify-between items-start border-b pb-2 mb-2">
                <div>
                  <span class="text-[10px] text-gray-400">{str(d['closed_at'])[:10]} 成約</span>
                  <h4 class="font-bold text-sm text-gray-900 line-clamp-1">{d['title']}</h4>
                  <p class="text-xs text-gray-600 mt-0.5">購入店: <strong class="text-blue-900">{d['name']}</strong></p>
                </div>
                <a href="/items/{d['item_id']}?mode={mode}" class="text-[10px] bg-gray-100 text-gray-700 px-2 py-1 rounded hover:bg-gray-200">詳細</a>
              </div>
              <div class="flex justify-between text-xs items-center bg-gray-50 p-2 rounded">
                <span class="text-gray-500">売値: ¥{d['deal_price']:,} (手数料: -¥{d['fee_amount']:,})</span>
                <span class="font-black text-emerald-700 text-sm">手取: ¥{net:,}</span>
              </div>
            </div>
            """

        c.execute("""
            SELECT d.id, d.closed_at, i.title, s.name, d.deal_price, i.id as item_id
            FROM deals d JOIN items i ON d.item_id = i.id JOIN shops s ON d.seller_shop_id = s.id
            WHERE d.buyer_shop_id = ? ORDER BY d.closed_at DESC
        """, (selected_shop_id,))
        for d in c.fetchall():
            buy_deals_html += f"""
            <div class="bg-white border rounded-xl p-3 shadow-sm flex flex-col justify-between">
              <div class="flex justify-between items-start border-b pb-2 mb-2">
                <div>
                  <span class="text-[10px] text-gray-400">{str(d['closed_at'])[:10]} 購入</span>
                  <h4 class="font-bold text-sm text-gray-900 line-clamp-1">{d['title']}</h4>
                  <p class="text-xs text-gray-600 mt-0.5">出品店: <strong class="text-blue-900">{d['name']}</strong></p>
                </div>
                <a href="/items/{d['item_id']}?mode={mode}" class="text-[10px] bg-gray-100 text-gray-700 px-2 py-1 rounded hover:bg-gray-200">詳細</a>
              </div>
              <div class="flex justify-between text-xs items-center bg-gray-50 p-2 rounded">
                <span class="text-gray-500">購入価格(税込)</span>
                <span class="font-black text-red-600 text-sm">¥{d['deal_price']:,}</span>
              </div>
            </div>
            """

    conn.close()

    content = f"""
    <div class="space-y-5">
      <div class="bg-white rounded-2xl p-4 shadow-sm border space-y-3">
        <h1 class="font-black text-base text-gray-900 flex items-center gap-2"><span>👤</span> 公式 でらイド 店舗マイページ</h1>
        <form action="/mypage" method="get" class="flex gap-2">
          <input type="hidden" name="mode" value="{mode}">
          <select name="shop_id" class="flex-1 border rounded-xl p-2.5 text-xs bg-gray-50 font-bold" onchange="this.form.submit()">
            <option value="">▼ 店舗を選択してください</option>
            {shop_options}
          </select>
          <button type="submit" class="bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow">表示</button>
        </form>
      </div>
      {f'''
      <div><h3 class="font-bold text-sm text-gray-900 mb-2 flex items-center gap-1.5"><span>🛍️</span> 購入した履歴（買手）</h3><div class="space-y-2">{buy_deals_html or '<p class="text-xs text-gray-400 py-6 text-center border border-dashed rounded-xl bg-white">購入履歴はありません</p>'}</div></div>
      <div><h3 class="font-bold text-sm text-gray-900 mb-2 flex items-center gap-1.5"><span>🎉</span> 出品して成約した履歴（売手）</h3><div class="space-y-2">{sell_deals_html or '<p class="text-xs text-gray-400 py-6 text-center border border-dashed rounded-xl bg-white">成約履歴はありません</p>'}</div></div>
      ''' if selected_shop_id else '<div class="text-center py-12 text-xs text-gray-400 bg-white rounded-2xl border border-dashed">店舗を選択すると取引履歴が表示されます</div>'}
    </div>
    """
    return render_page(content, active_tab="mypage", mode=mode)

# --- F. 管理者画面 ---
def render_admin(mode="buyer"):
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT deals.id, deals.closed_at, items.title, seller.name as s_name, buyer.name as b_name, deals.deal_price, deals.fee_amount 
                 FROM deals JOIN items ON deals.item_id = items.id 
                 JOIN shops as seller ON deals.seller_shop_id = seller.id 
                 JOIN shops as buyer ON deals.buyer_shop_id = buyer.id ORDER BY deals.closed_at DESC""")
    deals = c.fetchall()
    conn.close()
    
    total_fee = sum(d['fee_amount'] for d in deals)
    rows = "".join([f"""<tr class="border-b text-xs hover:bg-gray-50">
      <td class="p-3 text-gray-600">{str(d['closed_at'])[:10]}</td>
      <td class="p-3 font-bold text-gray-800">{d['title']}</td>
      <td class="p-3 text-gray-700">
        <span class="text-[10px] text-blue-600 bg-blue-50 px-1 rounded border">売手</span> {d['s_name']}<br>
        <span class="text-[10px] text-green-600 bg-green-50 px-1 rounded border mt-1 inline-block">買手</span> {d['b_name']}
      </td>
      <td class="p-3 text-right">¥{d['deal_price']:,}</td>
      <td class="p-3 text-right font-bold text-red-600">¥{d['fee_amount']:,}</td>
      <td class="p-3 text-right font-black text-emerald-700">¥{(d['deal_price'] - d['fee_amount']):,}</td>
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
          <div><h1 class="font-black text-base flex items-center gap-1.5">⚙️ 公式 でらイド 成約明細台帳</h1><p class="text-[11px] text-blue-200">成約件数: {len(deals)}件 / 手数料率: 10%</p></div>
          <div class="text-right"><span class="text-[10px] text-blue-200 block">累計手数料</span><span class="text-xl font-black text-yellow-300">¥{total_fee:,}</span></div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left min-w-[600px]">
            <tr class="bg-gray-100 border-b border-gray-300 text-[11px] text-gray-600 uppercase">
              <th class="p-3 font-semibold">成約日</th><th class="p-3 font-semibold">成約商品</th><th class="p-3 font-semibold">取引店舗</th>
              <th class="p-3 text-right font-semibold">成約価格(税込)</th><th class="p-3 text-right font-semibold">手数料(10%)</th><th class="p-3 text-right font-semibold">売手受取額</th>
            </tr>
            {rows}
          </table>
        </div>
      </div>
    </div>
    """
    return render_page(content, active_tab="admin", mode=mode)

# --- G. CSVダウンロード ---
def download_csv(handler_obj):
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT deals.id, deals.closed_at, items.title, seller.name as s_name, buyer.name as b_name, deals.deal_price, deals.fee_amount 
                 FROM deals JOIN items ON deals.item_id = items.id 
                 JOIN shops as seller ON deals.seller_shop_id = seller.id 
                 JOIN shops as buyer ON deals.buyer_shop_id = buyer.id ORDER BY deals.closed_at DESC""")
    deals = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['取引ID', '成約日時', '商品名', '出品店舗(売手)', '購入店舗(買手)', '決済額(成約価格)', 'でらイド手数料(10%)', '出品者受取額'])
    for d in deals:
        writer.writerow([d['id'], d['closed_at'], d['title'], d['s_name'], d['b_name'], d['deal_price'], d['fee_amount'], d['deal_price'] - d['fee_amount']])
        
    csv_data = output.getvalue().encode('shift_jis', errors='replace')
    handler_obj.send_response(200)
    handler_obj.send_header('Content-Type', 'text/csv; charset=Shift_JIS')
    handler_obj.send_header('Content-Disposition', f'attachment; filename="deride_deals_{datetime.now().strftime("%Y%m%d")}.csv"')
    handler_obj.end_headers()
    handler_obj.wfile.write(csv_data)

# ==========================================
# 4. 通信リクエスト処理
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
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)
            mode = query.get('mode', ['buyer'])[0]

            if path == '/banner.jpg':
                candidates = ['banner.jpg', os.path.join(os.path.dirname(__file__), 'banner.jpg'), os.path.join(os.path.dirname(__file__), '..', 'banner.jpg')]
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
                
            elif path in ('', '/', '/index.html'): self.send_html(render_home(mode=mode))
            elif path == '/likes': self.send_html(render_likes(mode=mode))
            elif path == '/sell': self.send_html(render_sell(mode="seller"))
            elif path == '/mypage': 
                shop_id = query.get('shop_id', [''])[0]
                self.send_html(render_mypage(shop_id, mode=mode))
            elif path.startswith('/items/') and path.endswith('/edit'):
                item_id = path.split('/')[2]
                self.send_html(render_sell(edit_item_id=item_id, mode="seller"))
            elif path.startswith('/items/'): 
                raw_id = path.split('/')[-1]
                self.send_html(render_detail(raw_id, mode=mode))
            elif path == '/admin/deals': self.send_html(render_admin(mode=mode))
            elif path == '/admin/deals/download': download_csv(self)
            else: self.send_html(render_home(mode=mode))
        except Exception as e:
            self.send_html(f"<h1>処理エラー</h1><pre>{traceback.format_exc()}</pre><p><a href='/'>トップに戻る</a></p>")

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)
            mode = query.get('mode', ['buyer'])[0]

            length = int(self.headers.get('Content-Length', 0))
            data = urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8'))
            conn = get_db()
            c = conn.cursor()

            if path == '/items/create':
                shop_id_val = data.get('shop_id', ['1'])[0] or '1'
                c.execute("""
                    INSERT INTO items (
                        shop_id, category, title, price, description, status, created_at, image_data,
                        brand, item_condition, shipping_fee, shipping_method, shipping_area, shipping_days, likes_count
                    ) VALUES (?, ?, ?, ?, ?, '出品中', ?, ?, ?, '未使用に近い', '送料込み', '直接引き取り', '愛知県', '1〜2日で発送', 0)
                """, (
                    shop_id_val, 
                    data.get('category', ['バイク'])[0], 
                    data.get('title', ['無題'])[0], 
                    int(data.get('price', ['0'])[0] or 0), 
                    data.get('description', [''])[0], 
                    datetime.now().strftime('%Y-%m-%d %H:%M'), 
                    data.get('image_data_json', [''])[0],
                    data.get('brand', ['ホンダ'])[0]
                ))
                conn.commit()
                self.send_redirect(f'/?mode={mode}')

            elif path == '/items/update':
                item_id = data.get('item_id', [''])[0]
                shop_id_val = data.get('shop_id', ['1'])[0] or '1'
                img_json = data.get('image_data_json', [''])[0]
                
                # 画像が新しく選ばれていれば更新、なければそのまま保持
                if img_json:
                    c.execute("""
                        UPDATE items SET shop_id=?, category=?, title=?, price=?, description=?, brand=?, image_data=? WHERE id=?
                    """, (
                        shop_id_val, data.get('category', ['バイク'])[0], data.get('title', [''])[0], 
                        int(data.get('price', ['0'])[0] or 0), data.get('description', [''])[0], data.get('brand', ['ホンダ'])[0],
                        img_json, item_id
                    ))
                else:
                    c.execute("""
                        UPDATE items SET shop_id=?, category=?, title=?, price=?, description=?, brand=? WHERE id=?
                    """, (
                        shop_id_val, data.get('category', ['バイク'])[0], data.get('title', [''])[0], 
                        int(data.get('price', ['0'])[0] or 0), data.get('description', [''])[0], data.get('brand', ['ホンダ'])[0],
                        item_id
                    ))
                conn.commit()
                self.send_redirect(f"/items/{item_id}?mode={mode}")

            elif path == '/items/like':
                item_id = data.get('item_id', [''])[0]
                c.execute("UPDATE items SET likes_count = COALESCE(likes_count, 0) + 1 WHERE id = ?", (item_id,))
                conn.commit()
                self.send_redirect(f"/items/{item_id}?mode={mode}")

            elif path == '/items/delete':
                item_id = data.get('item_id', [''])[0]
                c.execute("DELETE FROM items WHERE id = ?", (item_id,))
                c.execute("DELETE FROM comments WHERE id = ?", (item_id,))
                conn.commit()
                self.send_redirect(f'/?mode={mode}')

            elif path == '/comments/create':
                item_id = data.get('item_id', [''])[0]
                shop_id = data.get('shop_id', ['1'])[0]
                c.execute("INSERT INTO comments (item_id, shop_id, message, created_at) VALUES (?, ?, ?, ?)",
                          (item_id, shop_id, data.get('message', [''])[0], datetime.now().strftime('%Y-%m-%d %H:%M')))
                conn.commit()
                self.send_redirect(f"/items/{item_id}?mode={mode}")

            elif path == '/deals/close':
                item_id = data.get('item_id', [''])[0]
                seller_shop_id = data.get('seller_shop_id', ['1'])[0]
                buyer_shop_id = data.get('buyer_shop_id', ['2'])[0]
                price = int(data.get('price', ['0'])[0] or 0)
                fee_10pct = int(price * 0.10)
                c.execute("INSERT INTO deals (item_id, seller_shop_id, buyer_shop_id, deal_price, fee_amount, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
                          (item_id, seller_shop_id, buyer_shop_id, price, fee_10pct, datetime.now().strftime('%Y-%m-%d %H:%M')))
                c.execute("UPDATE items SET status = '成約済み' WHERE id = ?", (item_id,))
                conn.commit()
                self.send_redirect(f"/items/{item_id}?mode={mode}")

            conn.close()
        except Exception as e:
            self.send_html(f"<h1>処理エラー</h1><pre>{traceback.format_exc()}</pre><p><a href='/'>トップに戻る</a></p>")

Handler = handler

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", port), handler) as httpd:
        print(f"★ 起動中 PORT: {port}")
        httpd.serve_forever()
