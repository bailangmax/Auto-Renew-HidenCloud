#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import random
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
# 简单反自动化特征
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
# 获取当前出口 IP
# ============================================================

def get_current_ip(proxy_server=None):

    proxies = (
        {
            "http": proxy_server,
            "https": proxy_server
        }
        if (proxy_server and IS_PROXY)
        else None
    )

    try:

        resp = requests.get(
            "https://api.ip.sb/ip",
            proxies=proxies,
            timeout=15
        )

        if resp.status_code == 200:
            return resp.text.strip()

        return "获取失败"

    except Exception as e:

        log(f"❌ 获取出口IP失败: {e}")

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

        log("⚠️ Telegram 未配置，跳过通知")

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
                f"{name[:2]}****{name[-2:]}@{domain}"
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

        resp = requests.post(
            url,
            json=payload,
            timeout=10,
            proxies=REQUESTS_PROXIES
        )

        if resp.status_code == 200:

            log("📨 Telegram 通知发送成功")

            return True

        log(
            f"⚠️ Telegram 返回状态码："
            f"{resp.status_code}"
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
# 注意：
# 不主动模拟/破解 Cloudflare。
# 这里只负责等待页面上的 Challenge 完成。
# ============================================================

def wait_for_cloudflare(
    page,
    timeout=60
):

    log("🛡️ 检查 Cloudflare 验证...")

    iframe_selector = (
        'iframe[src*="challenges.cloudflare.com"]'
    )

    start_time = time.time()

    found = False

    while time.time() - start_time < timeout:

        try:

            count = page.locator(
                iframe_selector
            ).count()

            if count > 0:

                if not found:

                    log(
                        "🛡️ 检测到 Cloudflare Challenge，"
                        "等待验证完成..."
                    )

                    found = True

                # 页面可能已经完成验证
                # 这里不主动点击 CF 控件
                time.sleep(1)

                continue

            # 没有 CF iframe
            if found:

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
        "⚠️ Cloudflare 等待超时，"
        "继续检查页面"
    )

    return False


# 保留旧函数名称，兼容其他代码
def handle_cloudflare(page):

    return wait_for_cloudflare(
        page,
        timeout=60
    )


# ============================================================
# 登录
# ============================================================

def login(page):

    # --------------------------------------------------------
    # Cookie 登录
    # --------------------------------------------------------

    if COOKIE_VALUE:

        log("📇 尝试 Cookie 登录...")

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
                            int(time.time()) + 3600 * 24 * 365,

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

                log("✅ Cookie 登录成功！")

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
            "❌ Cookie 登录失败，"
            "且没有配置账号密码"
        )

        return False


    log("💣 尝试账号密码登录...")


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


        log(
            "❌ 页面中没有找到 Server ID"
        )

        return None


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

            r"Due date\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",

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
# 查找可见 Create Invoice
# ============================================================

def find_create_invoice(page):

    # --------------------------------------------------------
    # 方案 1：当前显示的 Modal 内寻找
    # --------------------------------------------------------

    modal_selectors = [

        "div.modal.show",

        "div.modal.fade.show",

        '[role="dialog"]',

        ".modal-dialog"

    ]


    for selector in modal_selectors:

        try:

            modals = page.locator(selector)

            count = modals.count()

            for i in range(count):

                modal = modals.nth(i)

                try:

                    if not modal.is_visible():
                        continue
                except Exception:
                    continue


                log(
                    f"🔎 在弹窗中寻找 Create Invoice "
                    f"({selector})..."
                )


                # button
                buttons = modal.locator(
                    "button"
                )

                for j in range(buttons.count()):

                    button = buttons.nth(j)

                    try:

                        if not button.is_visible():
                            continue

                        text = (
                            button.inner_text()
                            .strip()
                        )

                        value = (
                            button.get_attribute(
                                "value"
                            )
                            or ""
                        )

                        combined = (
                            text + " " + value
                        ).strip()


                        if re.search(
                            r"create\s*invoice",
                            combined,
                            re.IGNORECASE
                        ):

                            log(
                                f"✅ 找到 Create Invoice "
                                f"按钮：{combined}"
                            )

                            return button

                    except Exception:
                        continue


                # input submit
                inputs = modal.locator(
                    'input[type="submit"], '
                    'input[type="button"]'
                )


                for j in range(inputs.count()):

                    element = inputs.nth(j)

                    try:

                        if not element.is_visible():
                            continue


                        value = (
                            element.get_attribute(
                                "value"
                            )
                            or ""
                        )


                        if re.search(
                            r"create\s*invoice",
                            value,
                            re.IGNORECASE
                        ):

                            log(
                                "✅ 找到 Create Invoice "
                                "提交按钮"
                            )

                            return element

                    except Exception:
                        continue


                # 文本
                text_elements = modal.get_by_text(
                    re.compile(
                        r"^\s*Create\s+Invoice\s*$",
                        re.IGNORECASE
                    )
                )


                for j in range(
                    text_elements.count()
                ):

                    element = text_elements.nth(j)

                    try:

                        if element.is_visible():

                            log(
                                "✅ 找到 Create Invoice 文本元素"
                            )

                            return element

                    except Exception:
                        continue


        except Exception as e:

            log(
                f"⚠️ Modal 搜索异常：{e}"
            )


    # --------------------------------------------------------
    # 方案 2：全页面寻找
    # --------------------------------------------------------

    log(
        "🔎 在整个页面寻找 Create Invoice..."
    )


    candidates = [

        'button:has-text("Create Invoice")',

        'a:has-text("Create Invoice")',

        'input[value*="Create Invoice"]',

        'input[value*="create invoice" i]'

    ]


    for selector in candidates:

        try:

            elements = page.locator(
                selector
            )

            count = elements.count()


            for i in range(count):

                element = elements.nth(i)

                try:

                    if not element.is_visible():
                        continue


                    log(
                        f"✅ 找到候选元素："
                        f"{selector}"
                    )

                    return element

                except Exception:

                    continue


        except Exception:

            continue


    # --------------------------------------------------------
    # 方案 3：get_by_role
    # --------------------------------------------------------

    try:

        elements = page.get_by_role(
            "button",
            name=re.compile(
                r"Create\s+Invoice",
                re.IGNORECASE
            )
        )


        for i in range(elements.count()):

            element = elements.nth(i)

            try:

                if element.is_visible():

                    log(
                        "✅ get_by_role 找到 "
                        "Create Invoice"
                    )

                    return element

            except Exception:
                continue


    except Exception:
        pass


    # --------------------------------------------------------
    # 方案 4：get_by_text
    # --------------------------------------------------------

    try:

        elements = page.get_by_text(
            re.compile(
                r"Create\s+Invoice",
                re.IGNORECASE
            )
        )


        for i in range(elements.count()):

            element = elements.nth(i)

            try:

                if element.is_visible():

                    log(
                        "✅ get_by_text 找到 "
                        "Create Invoice"
                    )

                    return element

            except Exception:
                continue


    except Exception:
        pass


    return None


# ============================================================
# 等待 Create Invoice 按钮
# ============================================================

def wait_for_create_invoice(
    page,
    timeout=60
):

    start = time.time()


    while time.time() - start < timeout:

        button = find_create_invoice(page)


        if button is not None:

            try:

                if button.is_visible():

                    # 检查是否 disabled
                    disabled = button.get_attribute(
                        "disabled"
                    )

                    aria_disabled = (
                        button.get_attribute(
                            "aria-disabled"
                        )
                    )


                    if (
                        disabled is None
                        and aria_disabled != "true"
                    ):

                        log(
                            "✅ Create Invoice 已可点击"
                        )

                        return button


                    log(
                        "⏳ Create Invoice 已找到，"
                        "但按钮暂不可用，继续等待..."
                    )


            except Exception:
                pass


        time.sleep(1)


    return None


# ============================================================
# 获取页面文本
# ============================================================

def get_body_text(page):

    try:

        return page.locator(
            "body"
        ).inner_text(
            timeout=5000
        )

    except Exception:

        return ""


# ============================================================
# 续期
# ============================================================

def renew_service(page):

    try:

        log("➡ 进入续期流程...")


        # ----------------------------------------------------
        # 进入服务器页面
        # ----------------------------------------------------

        if SERVICE_URL not in page.url:

            page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )


        handle_cloudflare(page)


        time.sleep(2)


        # ----------------------------------------------------
        # 点击 Renew
        # ----------------------------------------------------

        log("🔎 寻找 Renew 按钮...")


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

            return False


        log("🖱️ 点击 Renew...")


        renew_button.click(
            timeout=15000
        )


        log(
            "✅ Renew 点击完成，"
            "等待续期弹窗..."
        )


        time.sleep(2)


        # ----------------------------------------------------
        # 等待 Cloudflare
        # ----------------------------------------------------

        handle_cloudflare(
            page
        )


        # Cloudflare 完成以后再给网站 JS 时间
        log(
            "⏳ 等待网页完成弹窗初始化..."
        )

        time.sleep(5)


        # ----------------------------------------------------
        # 输出当前页面状态
        # ----------------------------------------------------

        log(
            f"📍 当前 URL：{page.url}"
        )


        # ----------------------------------------------------
        # 查找 Create Invoice
        # ----------------------------------------------------

        log(
            "🔎 开始寻找 Create Invoice..."
        )


        create_invoice = wait_for_create_invoice(
            page,
            timeout=60
        )


        if create_invoice is None:

            log(
                "❌ 60 秒内没有找到可点击的 "
                "Create Invoice"
            )


            # 输出当前页面中所有按钮文字
            try:

                log(
                    "🔍 当前页面可见按钮："
                )


                buttons = page.locator(
                    "button:visible"
                )


                for i in range(
                    min(buttons.count(), 50)
                ):

                    try:

                        txt = buttons.nth(i).inner_text().strip()

                        if txt:

                            log(
                                f"   BUTTON[{i}]: "
                                f"{txt}"
                            )

                    except Exception:

                        continue


            except Exception:
                pass


            # 输出弹窗文字
            try:

                log(
                    "🔍 当前可见弹窗内容："
                )


                modals = page.locator(
                    "div.modal.show:visible, "
                    "div.modal.fade.show:visible, "
                    '[role="dialog"]:visible'
                )


                for i in range(
                    modals.count()
                ):

                    try:

                        txt = (
                            modals.nth(i)
                            .inner_text()
                            .strip()
                        )

                        if txt:

                            log(
                                "----- 弹窗 -----"
                            )

                            log(txt[:3000])

                    except Exception:
                        continue


            except Exception:
                pass


            # 截图
            try:

                path = (
                    "/tmp/"
                    "hidencloud_create_invoice_not_found.png"
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


            return False


        # ----------------------------------------------------
        # 点击 Create Invoice
        # ----------------------------------------------------

        log(
            "🖱️ 点击 Create Invoice..."
        )


        try:

            create_invoice.scroll_into_view_if_needed(
                timeout=10000
            )

        except Exception:
            pass


        time.sleep(1)


        try:

            create_invoice.click(
                timeout=15000
            )

        except Exception as e:

            log(
                f"⚠️ 普通点击失败：{e}"
            )

            # 重新定位一次
            create_invoice = wait_for_create_invoice(
                page,
                timeout=10
            )


            if create_invoice is None:

                log(
                    "❌ Create Invoice 重新定位失败"
                )

                return False


            create_invoice.click(
                timeout=15000
            )


        log(
            "✅ Create Invoice 点击完成！"
        )


        # ----------------------------------------------------
        # 等待创建发票
        # ----------------------------------------------------

        log(
            "⏳ 等待发票创建..."
        )


        time.sleep(5)


        # 等待导航
        try:

            page.wait_for_load_state(
                "domcontentloaded",
                timeout=15000
            )

        except Exception:

            pass


        handle_cloudflare(page)


        time.sleep(3)


        log(
            f"📍 Create Invoice 后 URL："
            f"{page.url}"
        )


        # ----------------------------------------------------
        # 如果直接进入 Invoice
        # ----------------------------------------------------

        if "/payment/invoice/" in page.url:

            log(
                "🎉 已进入 Invoice 页面！"
            )

            return True


        # ----------------------------------------------------
        # 如果网页自动出现 Invoice 链接
        # ----------------------------------------------------

        try:

            invoice_links = page.locator(
                'a[href*="/payment/invoice/"]'
            )


            for i in range(
                invoice_links.count()
            ):

                link = invoice_links.nth(i)


                try:

                    if not link.is_visible():

                        continue


                    target_url = (
                        link.get_attribute(
                            "href"
                        )
                    )


                    if target_url:

                        log(
                            f"🧾 找到 Invoice："
                            f"{target_url}"
                        )


                        page.goto(
                            target_url,
                            wait_until="domcontentloaded",
                            timeout=60000
                        )


                        handle_cloudflare(page)


                        time.sleep(3)


                        if (
                            "/payment/invoice/"
                            in page.url
                        ):

                            log(
                                "🎉 已进入 Invoice 页面！"
                            )

                            return True


                except Exception:

                    continue


        except Exception:
            pass


        # ----------------------------------------------------
        # 检查成功文字
        # ----------------------------------------------------

        body = get_body_text(page)


        success_keywords = [

            "Invoice Created",

            "Invoice created",

            "Invoice",

            "invoice",

            "Success",

            "success",

            "Created",

            "created"

        ]


        for keyword in success_keywords:

            if keyword in body:

                log(
                    f"✅ 页面检测到结果："
                    f"{keyword}"
                )

                return True


        # ----------------------------------------------------
        # 最后刷新服务器页面
        # ----------------------------------------------------

        log(
            "🔄 刷新服务器页面检查续期结果..."
        )


        page.goto(
            SERVICE_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )


        handle_cloudflare(page)


        time.sleep(4)


        new_due = get_due_date(page)


        log(
            f"📅 当前 Due Date："
            f"{new_due}"
        )


        if new_due != "未知":

            return True


        log(
            "❌ 没有检测到续期结果"
        )

        return False


    except Exception as e:

        log(
            f"❌ 续费过程异常: {e}"
        )


        # ----------------------------------------------------
        # 保存错误截图
        # ----------------------------------------------------

        try:

            path = (
                "/tmp/"
                "hidencloud_renew_error.png"
            )


            page.screenshot(
                path=path,
                full_page=True
            )


            log(
                f"📸 已保存错误截图：{path}"
            )


        except Exception:
            pass


        return False


# ============================================================
# 主程序
# ============================================================

def main():

    global SERVICE_URL


    # --------------------------------------------------------
    # 检查登录凭证
    # --------------------------------------------------------

    if not COOKIE_VALUE and not (
        EMAIL and PASSWORD
    ):

        log(
            "❌ 缺少登录凭证"
        )

        sys.exit(1)


    # --------------------------------------------------------
    # Playwright
    # --------------------------------------------------------

    with sync_playwright() as p:

        browser = None


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
            # Context
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
                    "❌ 登录失败，退出"
                )

                sys.exit(1)


            # ------------------------------------------------
            # 获取 Server ID
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
            # 获取续期前时间
            # ------------------------------------------------

            old_due = get_due_date(
                page
            )


            log(
                f"📆 续费前到期时间："
                f"{old_due}"
            )


            # ------------------------------------------------
            # 续期
            # ------------------------------------------------

            renew_result = renew_service(
                page
            )


            if not renew_result:

                log(
                    "❌ Renew → Create Invoice "
                    "流程失败"
                )

                send_telegram_notification(
                    "❌ HidenCloud 续期失败",
                    old_due,
                    "未知"
                )

                sys.exit(1)


            # ------------------------------------------------
            # 等待服务器状态更新
            # ------------------------------------------------

            log(
                "⏳ 等待 HidenCloud 更新服务器状态..."
            )


            time.sleep(5)


            # ------------------------------------------------
            # 返回服务页面
            # ------------------------------------------------

            page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )


            handle_cloudflare(page)


            time.sleep(3)


            # ------------------------------------------------
            # 获取续期后日期
            # ------------------------------------------------

            new_due = get_due_date(
                page
            )


            log(
                f"📆 续费后到期时间："
                f"{new_due}"
            )


            # ------------------------------------------------
            # 判断
            # ------------------------------------------------

            if (
                old_due != new_due
                and new_due != "未知"
            ):

                status = (
                    "✅ 续期成功"
                )

                renew_exit_code = 0

                log(
                    "🎉 HidenCloud 续期成功！"
                )


            else:

                status = (
                    "❌ 续期失败或时间未变"
                )

                renew_exit_code = 1

                log(
                    "❌ Due Date 没有发生变化"
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
                renew_exit_code
            )


        except Exception as e:

            log(
                f"❌ 运行报错：{e}"
            )


            try:

                if "page" in locals():

                    page.screenshot(
                        path="/tmp/"
                             "hidencloud_fatal_error.png",
                        full_page=True
                    )

                    log(
                        "📸 已保存最终错误截图"
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
