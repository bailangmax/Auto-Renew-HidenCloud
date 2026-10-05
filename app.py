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

        # 确保在服务器管理页面
        if page.url != SERVICE_URL:
            page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

        time.sleep(2)

        # ---------------------------------------------------------
        # 第一步：寻找并点击 Renew
        # ---------------------------------------------------------
        log("🔎 寻找 Renew 按钮...")

        renew_btn = page.locator(
            'button:has-text("Renew"), '
            'a:has-text("Renew")'
        ).filter(visible=True).first

        try:
            renew_btn.wait_for(
                state="visible",
                timeout=15000
            )
        except Exception:
            # 备用：通过文字寻找
            renew_btn = page.get_by_text(
                "Renew",
                exact=True
            ).filter(visible=True).first

            renew_btn.wait_for(
                state="visible",
                timeout=15000
            )

        log("🖱️ 点击 Renew...")
        renew_btn.click()

        log("✅ Renew 点击完成，等待续期弹窗...")

        # 给 Bootstrap / JS 弹窗一点加载时间
        time.sleep(2)

        # ---------------------------------------------------------
        # 第二步：等待 Cloudflare
        # ---------------------------------------------------------
        log("🛡️ 检查 Cloudflare 验证...")

        cf_passed = handle_cloudflare(page)

        if cf_passed:
            log("✅ Cloudflare 验证完成！")
        else:
            log("⚠️ Cloudflare 验证未检测到自动完成状态，继续等待页面...")

        # Cloudflare / 弹窗 JS 可能还需要一点时间
        time.sleep(3)

        # ---------------------------------------------------------
        # 第三步：寻找 Create Invoice
        # ---------------------------------------------------------
        log("🔎 寻找 Create Invoice 按钮...")

        create_invoice = page.locator(
            'button:has-text("Create Invoice"), '
            'a:has-text("Create Invoice"), '
            'input[type="submit"][value*="Create Invoice"]'
        ).filter(visible=True).first

        try:
            create_invoice.wait_for(
                state="visible",
                timeout=30000
            )
        except Exception:
            log("⚠️ 第一种方式没有找到 Create Invoice，尝试备用定位...")

            create_invoice = page.get_by_text(
                "Create Invoice",
                exact=True
            ).filter(visible=True).first

            create_invoice.wait_for(
                state="visible",
                timeout=30000
            )

        log("✅ 找到 Create Invoice")
        log("🖱️ 点击 Create Invoice...")

        create_invoice.click()

        log("✅ Create Invoice 点击完成！")

        # ---------------------------------------------------------
        # 第四步：等待发票创建 / 页面跳转
        # ---------------------------------------------------------
        log("⏳ 等待发票创建...")

        time.sleep(5)

        # 等待页面完成导航或 DOM 更新
        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=15000
            )
        except Exception:
            pass

        # 再处理一次可能出现的 Cloudflare
        handle_cloudflare(page)

        time.sleep(3)

        log(f"📍 当前页面：{page.url}")

        # ---------------------------------------------------------
        # 第五步：判断是否已经进入 Invoice
        # ---------------------------------------------------------
        if "/payment/invoice/" in page.url:
            log("🎉 已进入 Invoice 页面！")
            return True

        # 如果没有自动跳转，尝试寻找 Invoice 链接
        invoice_link = page.locator(
            'a[href*="/payment/invoice/"]:visible'
        ).first

        if invoice_link.count() > 0:
            try:
                invoice_link.wait_for(
                    state="visible",
                    timeout=10000
                )

                target_url = invoice_link.get_attribute("href")

                if target_url:
                    log(f"🧾 找到 Invoice：{target_url}")
                    page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    handle_cloudflare(page)

                    time.sleep(3)

                    log("🎉 已进入 Invoice 页面！")
                    return True

            except Exception as e:
                log(f"⚠️ Invoice 链接处理失败：{e}")

        # ---------------------------------------------------------
        # 第六步：检查页面是否出现成功提示
        # ---------------------------------------------------------
        body = page.locator("body").inner_text()

        success_keywords = [
            "Invoice",
            "invoice",
            "Created",
            "created successfully",
            "Success",
            "success"
        ]

        for keyword in success_keywords:
            if keyword in body:
                log(f"✅ 页面检测到成功信息：{keyword}")
                return True

        log("❌ Create Invoice 后没有检测到成功结果。")
        return False

    except Exception as e:
        log(f"❌ 续费过程异常: {e}")

        # 出错时截图，方便 GitHub Actions 排查
        try:
            page.screenshot(
                path="/tmp/hidencloud_renew_error.png",
                full_page=True
            )
            log("📸 已保存错误截图：/tmp/hidencloud_renew_error.png")
        except Exception:
            pass

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
