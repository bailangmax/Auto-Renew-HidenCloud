#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, time, random, requests
from playwright.sync_api import sync_playwright

# --- 环境变量 ---
COOKIE_VALUE = os.environ.get('COOKIE_VALUE') or ""    # remember_web cookie 值，必填
EMAIL        = os.environ.get('EMAIL') or ""           # 登录邮箱,可选
PASSWORD     = os.environ.get('PASSWORD') or ""        # 登录密码,可选
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN') or ""    # Telegram Bot Token,可选
TG_CHAT_ID   = os.environ.get('TG_CHAT_ID') or ""      # Telegram Chat ID,可选

BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"

# --- 代理配置 ---
IS_PROXY      = os.environ.get('IS_PROXY', 'false').lower() == 'true'
PROXY_SERVER  = os.environ.get('PROXY_SERVER') or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""

def get_current_ip(proxy_server=None):
    proxies = {"http": proxy_server, "https": proxy_server} if (proxy_server and IS_PROXY) else None
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
        if resp.status_code == 200:
            return resp.text.strip()
        return "获取失败"
    except Exception as e:
        log(f"❌ 获取出口IP失败: {e}")
        return "获取失败"

def send_telegram_notification(status, old_due, new_due):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ Telegram 未配置，跳过通知")
        return False
    
    local_time = time.gmtime(time.time() + 8 * 3600)
    now = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        masked_email = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****' if EMAIL else "未知用户"

    text = (
        f"🎉 HidenCloud 续期通知\n\n"
        f"{status}\n"
        f"👤 账号: {masked_email}\n"
        f"📅 续期前到期：{old_due}\n"
        f"📅 续期后到期：{new_due}\n"
        f"🕒 续期时间：{now}"
    )
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10, proxies=REQUESTS_PROXIES)
        return resp.status_code == 200
    except Exception as e:
        log(f"❌ Telegram 通知异常: {e}")
        return False

def handle_cloudflare(page):
    iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
    if page.locator(iframe_selector).count() == 0:
        return True
    log("⚠️ 检测到 Cloudflare 验证，开始自动过验...")
    start_time = time.time()
    while time.time() - start_time < 45:
        if page.locator(iframe_selector).count() == 0:
            log("✅ Cloudflare 验证通过！")
            return True
        try:
            frame = page.frame_locator(iframe_selector)
            checkbox = frame.locator('input[type="checkbox"]')
            if checkbox.is_visible():
                log("🖱️ 点击 Cloudflare 验证复选框...")
                time.sleep(random.uniform(0.5, 1.5))
                checkbox.click()
                time.sleep(5)
            else:
                time.sleep(1)
        except Exception:
            pass
    return False

def login(page):
    if COOKIE_VALUE:
        log("📇 尝试 Cookie 登录...")
        try:
            page.context.add_cookies([{
                'name': 'remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d',
                'value': COOKIE_VALUE,
                'domain': 'dash.hidencloud.com',
                'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
                'httpOnly': True,
                'secure': True,
                'sameSite': 'Lax'
            }])
            page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
            handle_cloudflare(page)
            if "auth/login" not in page.url:
                log("✅ Cookie 登录成功！")
                return True
        except:
            pass

    if not EMAIL or not PASSWORD:
        return False
    log("💣 尝试账号密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        page.fill('input[name="email"]', EMAIL)
        page.fill('input[name="password"]', PASSWORD)
        handle_cloudflare(page)
        page.click('button[type="submit"]')
        time.sleep(3)
        handle_cloudflare(page)
        page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        return "auth/login" not in page.url
    except Exception as e:
        log(f"❌ 登录异常: {e}")
        return False

def get_server_id(page):
    try:
        handle_cloudflare(page)
        time.sleep(2)
        html = page.content()
        matches = re.findall(r'/service/(\d+)/manage', html)
        if matches:
            return matches[0]
        matches = re.findall(r'#(\d{4,})', html)
        if matches:
            return matches[0]
        return None
    except Exception as e:
        log(f"❌ 获取 Server ID 失败: {e}")
        return None

def get_due_date(page):
    try:
        if SERVICE_URL not in page.url:
            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        body_text = page.locator("body").inner_text()
        patterns = [
            r"Due date\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
            r"Due date\s*\n\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
            r"Due date.*?(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
    except Exception as e:
        log(f"❌ 获取 Due Date 失败: {e}")
    return "未知"

def renew_service(page):
    try:
        log("➡ 进入续期流程...")
        if page.url != SERVICE_URL:
            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)

        # 检查未使用的 Invoice 链接（避免重复创建）
        invoice_link = page.locator('a[href*="/payment/invoice/"]').first
        if invoice_link.count() > 0 and invoice_link.is_visible():
            target_url = invoice_link.get_attribute("href")
            log(f"💡 发现已有未支付的发票: {target_url}")
            page.goto(target_url)
        else:
            # 请求后端直接生成发票 POST
            log("🚀 尝试通过 API 请求发起发票生成...")
            csrf_token = page.locator('meta[name="csrf-token"]').get_attribute('content') if page.locator('meta[name="csrf-token"]').count() > 0 else ""
            
            # 使用 context API 提交请求
            response = page.request.post(
                f"{SERVICE_URL}/renew",
                headers={
                    "x-csrf-token": csrf_token,
                    "referer": SERVICE_URL
                }
            )
            log(f"📝 续费 API 响应状态: {response.status}")

            time.sleep(3)
            page.reload()
            handle_cloudflare(page)

        # 再次查找 Pay 按钮或订单链接
        log("🔎 寻找结算发票页面...")
        page.goto(f"{BASE_URL}/invoices", wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)

        unpaid_invoice = page.locator('a[href*="/payment/invoice/"]').first
        if unpaid_invoice.count() > 0:
            unpaid_invoice.click()
            handle_cloudflare(page)

            log("🔎 查找 'Pay' 按钮...")
            pay_btn = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible, form button[type="submit"]:visible').first
            pay_btn.wait_for(state="visible", timeout=15000)
            pay_btn.click()
            log("✅ 'Pay' 点击完成！")
            time.sleep(5)
            return True
        else:
            log("⚠️ 未在账单列表中找到未支付发票。")
            return False

    except Exception as e:
        log(f"❌ 续费过程异常: {e}")
        return False

def main():
    if not COOKIE_VALUE and not (EMAIL and PASSWORD):
        log("❌ 缺少登录凭证")
        sys.exit(1)

    global SERVICE_URL

    with sync_playwright() as p:
        try:
            log(f"🎯 当前出口IP: {get_current_ip(PROXY_SERVER)}")
            log("🚀 启动浏览器...")
            browser = p.chromium.launch(
                channel="chrome",
                headless=False,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                proxy={"server": PROXY_SERVER} if IS_PROXY else None
            )
            page = context.new_page()
            page.add_init_script(STEALTH_JS)

            if not login(page):
                sys.exit(1)

            server_id = get_server_id(page)
            if not server_id:
                log("❌ 无法获取 Server ID，退出。")
                sys.exit(1)
            SERVICE_URL = f"{BASE_URL}/service/{server_id}/manage"

            old_due = get_due_date(page)
            log(f"📆 续费前到期时间：{old_due}")

            renew_result = renew_service(page)

            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
            new_due = get_due_date(page)
            log(f"📆 续费后到期时间：{new_due}")

            if old_due != new_due and new_due != "未知":
                status = "✅ 续期成功"
                renew_exit_code = 0
            else:
                status = "❌ 续期失败或时间未变"
                renew_exit_code = 1

            send_telegram_notification(status, old_due, new_due)
            sys.exit(renew_exit_code)

        except Exception as e:
            log(f"❌ 运行报错: {e}")
            sys.exit(1)
        finally:
            if 'browser' in locals() and browser:
                browser.close()

if __name__ == "__main__":
    main()
