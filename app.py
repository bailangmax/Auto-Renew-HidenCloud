#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import requests

from playwright.sync_api import sync_playwright


# ============================================================
# 环境变量
# ============================================================

COOKIE_VALUE = os.environ.get("COOKIE_VALUE") or ""

EMAIL = os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("PASSWORD") or ""

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""


# ============================================================
# HidenCloud
# ============================================================

BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"

SERVICE_URL = ""


# ============================================================
# 代理
# ============================================================

IS_PROXY = os.environ.get(
    "IS_PROXY",
    "false"
).lower() == "true"

PROXY_SERVER = os.environ.get(
    "PROXY_SERVER"
) or "socks5://127.0.0.1:1080"

REQUESTS_PROXIES = (
    {
        "http": PROXY_SERVER,
        "https": PROXY_SERVER
    }
    if IS_PROXY
    else None
)


# ============================================================
# 日志
# ============================================================

def log(message):
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}",
        flush=True
    )


# ============================================================
# 浏览器初始化脚本
# ============================================================

STEALTH_JS = """
Object.defineProperty(
    navigator,
    'webdriver',
    {
        get: () => undefined
    }
);

window.chrome = {
    runtime: {}
};
"""


# ============================================================
# 获取出口 IP
# ============================================================

def get_current_ip(proxy_server=None):

    proxies = None

    if proxy_server and IS_PROXY:

        proxies = {
            "http": proxy_server,
            "https": proxy_server
        }

    try:

        response = requests.get(
            "https://api.ip.sb/ip",
            proxies=proxies,
            timeout=15
        )

        if response.status_code == 200:

            return response.text.strip()

        return "获取失败"

    except Exception as e:

        log(
            f"❌ 获取出口IP失败: {e}"
        )

        return "获取失败"


# ============================================================
# Telegram
# ============================================================

def send_telegram_notification(
    status,
    old_due,
    new_due
):

    if not TG_BOT_TOKEN or not TG_CHAT_ID:

        log(
            "⚠️ Telegram 未配置，跳过通知"
        )

        return False


    local_time = time.gmtime(
        time.time() + 8 * 3600
    )

    now = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        local_time
    )


    if "@" in EMAIL:

        name, domain = EMAIL.split(
            "@",
            1
        )

        if len(name) > 4:

            masked_email = (
                f"{name[:2]}****"
                f"{name[-2:]}@{domain}"
            )

        else:

            masked_email = (
                f"{name}@{domain}"
            )

    else:

        masked_email = (
            EMAIL[:2] + "****"
            if EMAIL
            else "未知用户"
        )


    text = (
        "🎉 HidenCloud 续期通知\n\n"
        f"{status}\n"
        f"👤 账号: {masked_email}\n"
        f"📅 续期前到期：{old_due}\n"
        f"📅 续期后到期：{new_due}\n"
        f"🕒 续期时间：{now}"
    )


    url = (
        f"https://api.telegram.org/"
        f"bot{TG_BOT_TOKEN}/sendMessage"
    )


    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text
    }


    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10,
            proxies=REQUESTS_PROXIES
        )

        if response.status_code == 200:

            log(
                "📨 Telegram 通知发送成功"
            )

            return True

        log(
            f"⚠️ Telegram 返回状态码："
            f"{response.status_code}"
        )

        return False

    except Exception as e:

        log(
            f"❌ Telegram 通知异常: {e}"
        )

        return False


# ============================================================
# Cloudflare
#
# 不主动破解 Cloudflare。
# 只等待 Challenge 页面完成。
# ============================================================

def handle_cloudflare(
    page,
    timeout=60
):

    iframe_selector = (
        'iframe[src*="challenges.cloudflare.com"]'
    )

    start_time = time.time()

    detected = False


    while time.time() - start_time < timeout:

        try:

            count = page.locator(
                iframe_selector
            ).count()


            if count > 0:

                if not detected:

                    log(
                        "🛡️ 检测到 Cloudflare 验证，"
                        "等待验证完成..."
                    )

                    detected = True

                time.sleep(1)

                continue


            if detected:

                log(
                    "✅ Cloudflare 验证完成！"
                )

            else:

                log(
                    "✅ 未检测到 Cloudflare Challenge"
                )

            return True


        except Exception:

            time.sleep(1)


    log(
        "⚠️ Cloudflare 等待超时"
    )

    return False


# ============================================================
# 登录
# ============================================================

def login(page):

    # --------------------------------------------------------
    # Cookie 登录
    # --------------------------------------------------------

    if COOKIE_VALUE:

        log(
            "📇 尝试 Cookie 登录..."
        )

        try:

            page.context.add_cookies(
                [
                    {
                        "name":
                            "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d",

                        "value":
                            COOKIE_VALUE,

                        "domain":
                            "dash.hidencloud.com",

                        "path":
                            "/",

                        "expires":
                            int(time.time())
                            + 3600 * 24 * 365,

                        "httpOnly":
                            True,

                        "secure":
                            True,

                        "sameSite":
                            "Lax"
                    }
                ]
            )


            page.goto(
                f"{BASE_URL}/dashboard",
                wait_until="domcontentloaded",
                timeout=60000
            )


            handle_cloudflare(page)


            if "auth/login" not in page.url:

                log(
                    "✅ Cookie 登录成功！"
                )

                return True


        except Exception as e:

            log(
                f"⚠️ Cookie 登录失败：{e}"
            )


    # --------------------------------------------------------
    # 账号密码登录
    # --------------------------------------------------------

    if not EMAIL or not PASSWORD:

        log(
            "❌ 没有可用的登录凭证"
        )

        return False


    log(
        "💣 尝试账号密码登录..."
    )


    try:

        page.goto(
            LOGIN_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )


        handle_cloudflare(page)


        page.fill(
            'input[name="email"]',
            EMAIL
        )

        page.fill(
            'input[name="password"]',
            PASSWORD
        )


        handle_cloudflare(page)


        page.click(
            'button[type="submit"]'
        )


        time.sleep(3)


        handle_cloudflare(page)


        page.goto(
            f"{BASE_URL}/dashboard",
            wait_until="domcontentloaded",
            timeout=60000
        )


        handle_cloudflare(page)


        if "auth/login" not in page.url:

            log(
                "✅ 账号密码登录成功！"
            )

            return True


        log(
            "❌ 账号密码登录失败"
        )

        return False


    except Exception as e:

        log(
            f"❌ 登录异常: {e}"
        )

        return False


# ============================================================
# 获取 Server ID
# ============================================================

def get_server_id(page):

    try:

        handle_cloudflare(page)

        time.sleep(2)


        html = page.content()


        matches = re.findall(
            r"/service/(\d+)/manage",
            html
        )


        if matches:

            return matches[0]


        matches = re.findall(
            r"#(\d{4,})",
            html
        )


        if matches:

            return matches[0]


    except Exception as e:

        log(
            f"❌ 获取 Server ID 失败: {e}"
        )


    return None


# ============================================================
# 获取 Due Date
# ============================================================

def get_due_date(page):

    try:

        if SERVICE_URL not in page.url:

            page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )


        handle_cloudflare(page)


        time.sleep(2)


        body_text = page.locator(
            "body"
        ).inner_text()


        patterns = [

            r"Due date\s+"
            r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",

            r"Due date\s*\n\s*"
            r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",

            r"Due date.*?"
            r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"

        ]


        for pattern in patterns:

            match = re.search(
                pattern,
                body_text,
                re.IGNORECASE | re.DOTALL
            )

            if match:

                return match.group(1).strip()


    except Exception as e:

        log(
            f"❌ 获取 Due Date 失败: {e}"
        )


    return "未知"


# ============================================================
# 查找 Create Invoice
# ============================================================

def find_create_invoice(page):

    selectors = [

        'button:has-text("Create Invoice")',

        'a:has-text("Create Invoice")',

        'input[value*="Create Invoice"]',

        '[role="button"]:has-text("Create Invoice")'

    ]


    for selector in selectors:

        try:

            elements = page.locator(
                selector
            )


            count = elements.count()


            for i in range(count):

                element = elements.nth(i)


                try:

                    if element.is_visible():

                        return element

                except Exception:

                    continue


        except Exception:

            continue


    return None


# ============================================================
# 查找 Pay Now
# ============================================================

def find_pay_now(page):

    selectors = [

        'button:has-text("Pay Now")',

        'a:has-text("Pay Now")',

        '[role="button"]:has-text("Pay Now")',

        'input[value*="Pay Now"]'

    ]


    for selector in selectors:

        try:

            elements = page.locator(
                selector
            )


            count = elements.count()


            for i in range(count):

                element = elements.nth(i)


                try:

                    if element.is_visible():

                        return element

                except Exception:

                    continue


        except Exception:

            continue


    return None


# ============================================================
# 打印当前页面按钮
# ============================================================

def debug_buttons(page):

    log(
        "🔍 当前页面可见按钮："
    )


    try:

        buttons = page.locator(
            "button:visible"
        )


        total = buttons.count()


        for i in range(
            min(total, 50)
        ):

            try:

                text = (
                    buttons.nth(i)
                    .inner_text()
                    .strip()
                )


                if text:

                    log(
                        f"   BUTTON[{i}]: {text}"
                    )

            except Exception:

                continue


    except Exception:
        pass


# ============================================================
# 保存截图
# ============================================================

def save_screenshot(
    page,
    filename
):

    try:

        path = (
            "/tmp/"
            + filename
        )


        page.screenshot(
            path=path,
            full_page=True
        )


        log(
            f"📸 已保存截图：{path}"
        )


    except Exception as e:

        log(
            f"⚠️ 保存截图失败：{e}"
        )


# ============================================================
# 等待 Create Invoice
# ============================================================

def wait_create_invoice_or_pay_now(
    page,
    timeout=60
):

    log(
        "🔎 等待 Create Invoice / Pay Now..."
    )


    start = time.time()


    while time.time() - start < timeout:

        # ====================================================
        # 第一优先级：Create Invoice
        # ====================================================

        create_invoice = find_create_invoice(
            page
        )


        if create_invoice:

            log(
                "✅ 找到 Create Invoice！"
            )

            return (
                "create_invoice",
                create_invoice
            )


        # ====================================================
        # 第二优先级：Pay Now
        #
        # 你的最新日志已经证明：
        #
        # BUTTON[11]: Pay Now
        #
        # 所以这里认为 Invoice 已经创建。
        # ====================================================

        pay_now = find_pay_now(
            page
        )


        if pay_now:

            log(
                "✅ 检测到 Pay Now！"
            )

            log(
                "💡 当前页面已经存在付款按钮，"
                "说明续期 Invoice 已经生成。"
            )

            return (
                "pay_now",
                pay_now
            )


        # ====================================================
        # 继续等待
        # ====================================================

        time.sleep(1)


    return (
        None,
        None
    )


# ============================================================
# 点击按钮
# ============================================================

def click_element(
    element,
    name
):

    try:

        element.scroll_into_view_if_needed(
            timeout=10000
        )

    except Exception:
        pass


    time.sleep(1)


    try:

        log(
            f"🖱️ 点击 {name}..."
        )


        element.click(
            timeout=15000
        )


        log(
            f"✅ {name} 点击成功"
        )


        return True


    except Exception as e:

        log(
            f"⚠️ {name} 普通点击失败：{e}"
        )


        try:

            element.click(
                force=True,
                timeout=10000
            )


            log(
                f"✅ {name} 强制点击成功"
            )


            return True


        except Exception as e2:

            log(
                f"❌ {name} 点击失败：{e2}"
            )


            return False


# ============================================================
# 续期主流程
# ============================================================

def renew_service(page):

    try:

        log(
            "➡ 进入续期流程..."
        )


        # ----------------------------------------------------
        # 打开服务页面
        # ----------------------------------------------------

        if SERVICE_URL not in page.url:

            page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )


        handle_cloudflare(page)


        time.sleep(3)


        # ----------------------------------------------------
        # 找 Renew
        # ----------------------------------------------------

        log(
            "🔎 寻找 Renew 按钮..."
        )


        renew_button = None


        selectors = [

            'button:has-text("Renew")',

            'a:has-text("Renew")',

            '[role="button"]:has-text("Renew")'

        ]


        for selector in selectors:

            try:

                elements = page.locator(
                    selector
                )


                for i in range(
                    elements.count()
                ):

                    element = elements.nth(i)


                    try:

                        if element.is_visible():

                            renew_button = element

                            break

                    except Exception:

                        continue


                if renew_button:

                    break


            except Exception:

                continue


        if renew_button is None:

            log(
                "❌ 找不到 Renew 按钮"
            )

            debug_buttons(page)

            save_screenshot(
                page,
                "hidencloud_no_renew.png"
            )

            return False


        # ----------------------------------------------------
        # 点击 Renew
        # ----------------------------------------------------

        if not click_element(
            renew_button,
            "Renew"
        ):

            return False


        log(
            "⏳ Renew 点击完成，等待弹窗..."
        )


        time.sleep(3)


        # ----------------------------------------------------
        # Cloudflare
        # ----------------------------------------------------

        handle_cloudflare(
            page,
            timeout=60
        )


        log(
            "⏳ Cloudflare 后等待页面更新..."
        )


        time.sleep(5)


        # ----------------------------------------------------
        # 当前 URL
        # ----------------------------------------------------

        log(
            f"📍 当前 URL：{page.url}"
        )


        # ----------------------------------------------------
        # 等待 Create Invoice 或 Pay Now
        # ----------------------------------------------------

        result_type, element = (
            wait_create_invoice_or_pay_now(
                page,
                timeout=30
            )
        )


        # ====================================================
        # 情况 A
        #
        # 找到 Create Invoice
        # ====================================================

        if result_type == "create_invoice":

            log(
                "🎯 按照正常流程点击 Create Invoice"
            )


            if not click_element(
                element,
                "Create Invoice"
            ):

                return False


            log(
                "⏳ 等待 Invoice 创建..."
            )


            time.sleep(6)


            handle_cloudflare(
                page,
                timeout=30
            )


            time.sleep(3)


        # ====================================================
        # 情况 B
        #
        # 没有 Create Invoice，但是已经有 Pay Now
        # ====================================================

        elif result_type == "pay_now":

            log(
                "🎯 页面没有 Create Invoice，"
                "但已经出现 Pay Now。"
            )


            log(
                "✅ 判断：Invoice 已经创建。"
            )


        # ====================================================
        # 情况 C
        # ====================================================

        else:

            log(
                "❌ 30 秒内既没有找到 "
                "Create Invoice，也没有找到 Pay Now"
            )


            debug_buttons(page)


            # 打印页面关键文字
            try:

                body = page.locator(
                    "body"
                ).inner_text()


                log(
                    "🔍 当前页面关键内容："
                )


                log(
                    body[:5000]
                )


            except Exception:
                pass


            save_screenshot(
                page,
                "hidencloud_invoice_not_found.png"
            )


            return False


        # ====================================================
        # 到这里：
        #
        # Invoice 已经创建
        #
        # 现在重新查找 Pay Now
        # ====================================================

        log(
            "🔎 检查 Pay Now..."
        )


        pay_now = None


        for _ in range(30):

            pay_now = find_pay_now(
                page
            )


            if pay_now:

                break


            time.sleep(1)


        # ====================================================
        # 如果存在 Pay Now
        # ====================================================

        if pay_now:

            log(
                "💳 检测到 Pay Now"
            )


            log(
                "🖱️ 点击 Pay Now..."
            )


            if not click_element(
                pay_now,
                "Pay Now"
            ):

                log(
                    "⚠️ Pay Now 点击失败"
                )


            else:

                log(
                    "⏳ 等待支付/续期结果..."
                )


                time.sleep(6)


                try:

                    page.wait_for_load_state(
                        "domcontentloaded",
                        timeout=15000
                    )

                except Exception:
                    pass


                handle_cloudflare(
                    page,
                    timeout=30
                )


                time.sleep(4)


                log(
                    f"📍 Pay Now 后 URL："
                    f"{page.url}"
                )


        else:

            log(
                "ℹ️ 当前没有 Pay Now，"
                "可能 Invoice 创建后已经自动完成续期。"
            )


        # ====================================================
        # 最终回到服务器页面
        # ====================================================

        log(
            "🔄 返回服务器管理页面..."
        )


        page.goto(
            SERVICE_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )


        handle_cloudflare(
            page,
            timeout=30
        )


        time.sleep(5)


        # ====================================================
        # 获取当前 Due Date
        # ====================================================

        current_due = get_due_date(
            page
        )


        log(
            f"📅 当前 Due Date："
            f"{current_due}"
        )


        # ====================================================
        # 这里只判断流程有没有完成
        #
        # old_due 与 new_due 的最终判断放 main()
        # ====================================================

        if current_due != "未知":

            log(
                "✅ 续期流程执行完成"
            )

            return True


        log(
            "❌ 无法读取续期后的 Due Date"
        )

        return False


    except Exception as e:

        log(
            f"❌ 续费过程异常：{e}"
        )


        save_screenshot(
            page,
            "hidencloud_renew_error.png"
        )


        return False


# ============================================================
# 主程序
# ============================================================

def main():

    global SERVICE_URL


    # --------------------------------------------------------
    # 登录凭证
    # --------------------------------------------------------

    if not COOKIE_VALUE and not (
        EMAIL and PASSWORD
    ):

        log(
            "❌ 缺少登录凭证"
        )

        sys.exit(1)


    browser = None


    with sync_playwright() as p:

        try:

            # ------------------------------------------------
            # IP
            # ------------------------------------------------

            current_ip = get_current_ip(
                PROXY_SERVER
            )


            log(
                f"🎯 当前出口IP："
                f"{current_ip}"
            )


            # ------------------------------------------------
            # 浏览器
            # ------------------------------------------------

            log(
                "🚀 启动浏览器..."
            )


            browser = p.chromium.launch(

                channel="chrome",

                headless=False,

                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--window-size=1920,1080"
                ]
            )


            # ------------------------------------------------
            # 浏览器 Context
            # ------------------------------------------------

            context = browser.new_context(

                viewport={
                    "width": 1920,
                    "height": 1080
                },

                user_agent=(
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/128.0.0.0 "
                    "Safari/537.36"
                ),

                proxy=(
                    {
                        "server":
                            PROXY_SERVER
                    }
                    if IS_PROXY
                    else None
                )
            )


            # ------------------------------------------------
            # 页面
            # ------------------------------------------------

            page = context.new_page()


            page.add_init_script(
                STEALTH_JS
            )


            # ------------------------------------------------
            # 登录
            # ------------------------------------------------

            if not login(page):

                log(
                    "❌ 登录失败"
                )

                sys.exit(1)


            # ------------------------------------------------
            # Server ID
            # ------------------------------------------------

            server_id = get_server_id(
                page
            )


            if not server_id:

                log(
                    "❌ 无法获取 Server ID"
                )

                sys.exit(1)


            SERVICE_URL = (
                f"{BASE_URL}/service/"
                f"{server_id}/manage"
            )


            log(
                f"🖥️ Server ID："
                f"{server_id}"
            )


            log(
                f"🔗 服务地址："
                f"{SERVICE_URL}"
            )


            # ------------------------------------------------
            # 续期前
            # ------------------------------------------------

            old_due = get_due_date(
                page
            )


            log(
                f"📆 续费前到期时间："
                f"{old_due}"
            )


            # ------------------------------------------------
            # 执行续期
            # ------------------------------------------------

            result = renew_service(
                page
            )


            if not result:

                log(
                    "❌ 续期流程失败"
                )


                send_telegram_notification(
                    "❌ HidenCloud 续期失败",
                    old_due,
                    "未知"
                )


                sys.exit(1)


            # ------------------------------------------------
            # 等待后台更新
            # ------------------------------------------------

            log(
                "⏳ 等待 HidenCloud 更新 Due Date..."
            )


            time.sleep(8)


            # ------------------------------------------------
            # 重新打开服务器页面
            # ------------------------------------------------

            page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )


            handle_cloudflare(
                page,
                timeout=30
            )


            time.sleep(5)


            # ------------------------------------------------
            # 获取续期后时间
            # ------------------------------------------------

            new_due = get_due_date(
                page
            )


            log(
                f"📆 续期后到期时间："
                f"{new_due}"
            )


            # ------------------------------------------------
            # 最终判断
            # ------------------------------------------------

            if (
                old_due != "未知"
                and new_due != "未知"
                and old_due != new_due
            ):

                status = (
                    "✅ HidenCloud 续期成功"
                )

                exit_code = 0


                log(
                    "🎉🎉🎉 续期成功！"
                )


                log(
                    f"📅 {old_due} → {new_due}"
                )


            else:

                status = (
                    "❌ HidenCloud 续期失败"
                )

                exit_code = 1


                log(
                    "❌ Due Date 没有变化"
                )


                log(
                    f"旧日期：{old_due}"
                )

                log(
                    f"新日期：{new_due}"
                )


            # ------------------------------------------------
            # Telegram
            # ------------------------------------------------

            send_telegram_notification(
                status,
                old_due,
                new_due
            )


            sys.exit(
                exit_code
            )


        except Exception as e:

            log(
                f"❌ 程序运行异常：{e}"
            )


            try:

                if "page" in locals():

                    save_screenshot(
                        page,
                        "hidencloud_fatal_error.png"
                    )

            except Exception:
                pass


            sys.exit(1)


        finally:

            if browser:

                try:

                    browser.close()

                except Exception:

                    pass


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":

    main()
