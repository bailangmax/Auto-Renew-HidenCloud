import os
import re
import time
import asyncio
import traceback
from datetime import datetime

import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# HidenCloud 自动续期
# ============================================================

BASE_URL = "https://dash.hidencloud.com"

# 你的服务器
SERVICE_ID = os.getenv("HIDENCLOUD_SERVICE_ID", "227636")

SERVICE_URL = os.getenv(
    "HIDENCLOUD_SERVICE_URL",
    f"{BASE_URL}/service/{SERVICE_ID}/manage"
)

# Cookie
HIDENCLOUD_COOKIE = os.getenv("HIDENCLOUD_COOKIE", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 是否无头
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

# 代理，可选
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()

# 等待时间
CLOUDFLARE_WAIT = 10
PAY_WAIT = 15


# ============================================================
# 日志
# ============================================================

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("⚠️ 未配置 Telegram，跳过通知")
        return

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=20,
        )

        log("📨 Telegram 通知发送成功")

    except Exception as e:
        log(f"⚠️ Telegram 发送失败：{e}")


# ============================================================
# Cookie
# ============================================================

def build_cookie():
    """
    支持：

    HIDENCLOUD_COOKIE=完整cookie值

    如果你的 Cookie 是：

    remember_web_xxxxx=xxxxxxxx

    也可以直接填写整个：

    remember_web_xxxxx=xxxxxxxx
    """

    if not HIDENCLOUD_COOKIE:
        return []

    cookie = HIDENCLOUD_COOKIE.strip()

    # 如果用户直接填写 name=value
    if "=" in cookie:
        name, value = cookie.split("=", 1)

        return [{
            "name": name.strip(),
            "value": value.strip(),
            "domain": "dash.hidencloud.com",
            "path": "/",
            "secure": True,
        }]

    # 兼容以前的 HidenCloud remember cookie
    return [{
        "name": "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989",
        "value": cookie,
        "domain": "dash.hidencloud.com",
        "path": "/",
        "secure": True,
    }]


# ============================================================
# Cloudflare
# ============================================================

async def wait_cloudflare(page, timeout=30):
    """
    不绕过 Cloudflare。
    这里只等待网站自己的验证完成。
    """

    start = time.time()

    while time.time() - start < timeout:

        try:
            url = page.url.lower()

            content = await page.locator("body").inner_text(
                timeout=3000
            )

            cf_text = (
                "checking your browser" in content.lower()
                or "verify you are human" in content.lower()
                or "just a moment" in content.lower()
                or "checking your browser before accessing" in content.lower()
            )

            challenge_frame = False

            for frame in page.frames:
                frame_url = frame.url.lower()

                if (
                    "challenges.cloudflare.com" in frame_url
                    or "challenge-platform" in frame_url
                ):
                    challenge_frame = True
                    break

            if not cf_text and not challenge_frame:
                log("✅ 未检测到 Cloudflare Challenge")
                return True

            log("⏳ 检测到 Cloudflare Challenge，等待验证...")

        except Exception:
            pass

        await asyncio.sleep(2)

    log("⚠️ Cloudflare 等待超时，继续执行")
    return False


# ============================================================
# 获取 Due Date
# ============================================================

async def get_due_date(page):
    try:
        await page.wait_for_load_state(
            "domcontentloaded",
            timeout=15000
        )
    except Exception:
        pass

    try:
        text = await page.locator("body").inner_text(timeout=10000)

        # 常见：
        # Due Date
        # 05 Oct 2026
        #
        # 也兼容：
        # Due Date: 05 Oct 2026

        patterns = [
            r"Due Date\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
            r"Due\s*Date\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:
                return match.group(1).strip()

    except Exception as e:
        log(f"⚠️ 获取 Due Date 失败：{e}")

    return None


# ============================================================
# 截图
# ============================================================

async def screenshot(page, filename):
    try:
        path = f"/tmp/{filename}"

        await page.screenshot(
            path=path,
            full_page=True
        )

        log(f"📸 截图保存：{path}")

    except Exception as e:
        log(f"⚠️ 截图失败：{e}")


# ============================================================
# DOM 调试
# ============================================================

async def debug_buttons(page):
    """
    打印所有 Frame 中的按钮和链接。
    """

    log("🔎 开始扫描当前页面所有按钮...")

    for frame_index, frame in enumerate(page.frames):

        try:
            log(
                f"📄 Frame[{frame_index}] "
                f"URL: {frame.url}"
            )

            elements = await frame.locator(
                "button, a, input[type='button'], "
                "input[type='submit']"
            ).all()

            index = 0

            for element in elements:

                try:

                    if not await element.is_visible():
                        continue

                    index += 1

                    text = ""

                    try:
                        text = await element.inner_text(
                            timeout=1000
                        )
                    except Exception:
                        pass

                    if not text:
                        try:
                            text = await element.get_attribute(
                                "value"
                            )
                        except Exception:
                            pass

                    href = ""

                    try:
                        href = await element.get_attribute(
                            "href"
                        )
                    except Exception:
                        pass

                    log(
                        f"  [{index}] "
                        f"{text.strip()[:100]} "
                        f"href={href}"
                    )

                except Exception:
                    continue

        except Exception:
            continue


# ============================================================
# 查找文字元素
# ============================================================

async def find_text_element(page, text):
    """
    在所有 frame 中寻找文字。
    """

    selectors = [
        f"button:has-text('{text}')",
        f"a:has-text('{text}')",
        f"[role='button']:has-text('{text}')",
        f"input[value*='{text}']",
    ]

    for frame in page.frames:

        for selector in selectors:

            try:

                locator = frame.locator(selector).first

                count = await locator.count()

                if count == 0:
                    continue

                if await locator.is_visible():
                    return locator

            except Exception:
                continue

    return None


# ============================================================
# 强力点击
# ============================================================

async def force_click(locator, name="按钮"):
    """
    解决：

    Element is outside of the viewport

    使用三级点击。
    """

    # --------------------------------------------------------
    # 方法 1：force=True
    # --------------------------------------------------------

    try:

        log(f"🖱️ {name}：尝试 force=True 点击...")

        await locator.click(
            force=True,
            timeout=10000
        )

        log(f"✅ {name} force 点击成功")

        return True

    except Exception as e:

        log(
            f"⚠️ {name} force 点击失败："
            f"{str(e)[:300]}"
        )

    # --------------------------------------------------------
    # 方法 2：DOM click
    # --------------------------------------------------------

    try:

        log(f"🖱️ {name}：尝试 JavaScript click()...")

        await locator.evaluate(
            """
            element => {
                element.scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });

                element.click();
            }
            """
        )

        log(f"✅ {name} JavaScript click 成功")

        return True

    except Exception as e:

        log(
            f"⚠️ {name} JavaScript click 失败："
            f"{str(e)[:300]}"
        )

    # --------------------------------------------------------
    # 方法 3：完整 MouseEvent
    # --------------------------------------------------------

    try:

        log(f"🖱️ {name}：尝试 JS MouseEvent...")

        await locator.evaluate(
            """
            element => {

                element.scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });

                const events = [
                    'pointerover',
                    'mouseover',
                    'pointerdown',
                    'mousedown',
                    'pointerup',
                    'mouseup',
                    'click'
                ];

                for (const eventName of events) {

                    element.dispatchEvent(
                        new MouseEvent(eventName, {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        })
                    );

                }
            }
            """
        )

        log(f"✅ {name} JS MouseEvent 成功")

        return True

    except Exception as e:

        log(
            f"❌ {name} 所有点击方式均失败："
            f"{str(e)[:300]}"
        )

        return False


# ============================================================
# 查找 Create Invoice
# ============================================================

async def find_create_invoice(page):

    log("🔎 寻找 Create Invoice...")

    return await find_text_element(
        page,
        "Create Invoice"
    )


# ============================================================
# 查找 Pay Now
# ============================================================

async def find_pay_now(page):

    log("🔎 寻找 Pay Now...")

    locator = await find_text_element(
        page,
        "Pay Now"
    )

    if locator:
        log("💳 检测到 Pay Now")

    return locator


# ============================================================
# 点击 Renew
# ============================================================

async def click_renew(page):

    log("🔎 寻找 Renew 按钮...")

    locator = await find_text_element(
        page,
        "Renew"
    )

    if not locator:

        log("❌ 没有找到 Renew")

        await debug_buttons(page)

        await screenshot(
            page,
            "hidencloud_renew_button_not_found.png"
        )

        return False

    log("✅ 找到 Renew 按钮")

    ok = await force_click(
        locator,
        "Renew"
    )

    if not ok:
        return False

    log("✅ Renew 点击完成")
    log("⏳ 等待续期弹窗 / Invoice 状态...")

    await asyncio.sleep(5)

    await wait_cloudflare(
        page,
        timeout=30
    )

    return True


# ============================================================
# 查找 Invoice / Pay Now
# ============================================================

async def wait_invoice_state(page, timeout=30):

    log("🔎 等待 Create Invoice / Pay Now...")

    start = time.time()

    while time.time() - start < timeout:

        # Create Invoice
        create_invoice = await find_create_invoice(page)

        if create_invoice:

            log("✅ 检测到 Create Invoice！")

            return "create_invoice", create_invoice

        # Pay Now
        pay_now = await find_pay_now(page)

        if pay_now:

            log("✅ 检测到 Pay Now！")
            log("💡 当前页面已经存在付款按钮，说明 Invoice 已经生成。")

            return "pay_now", pay_now

        await asyncio.sleep(1)

    return None, None


# ============================================================
# 点击 Create Invoice
# ============================================================

async def click_create_invoice(page, locator):

    log("🧾 点击 Create Invoice...")

    ok = await force_click(
        locator,
        "Create Invoice"
    )

    if not ok:
        return False

    log("⏳ Create Invoice 已点击，等待页面变化...")

    await asyncio.sleep(5)

    await wait_cloudflare(
        page,
        timeout=30
    )

    return True


# ============================================================
# 点击 Pay Now
# ============================================================

async def click_pay_now(page, locator):

    log("💳 准备点击 Pay Now...")

    # --------------------------------------------------------
    # 记录点击前状态
    # --------------------------------------------------------

    before_url = page.url

    log(f"📍 点击前 URL：{before_url}")

    # --------------------------------------------------------
    # 获取按钮信息
    # --------------------------------------------------------

    try:

        info = await locator.evaluate(
            """
            element => {

                const rect =
                    element.getBoundingClientRect();

                return {
                    text: element.innerText,
                    disabled: element.disabled,
                    type: element.type,
                    formAction:
                        element.form
                        ? element.form.action
                        : null,
                    formMethod:
                        element.form
                        ? element.form.method
                        : null,
                    rect: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    },
                    html: element.outerHTML
                };
            }
            """
        )

        log(
            f"🔍 Pay Now DOM 信息："
            f"{info}"
        )

    except Exception as e:

        log(
            f"⚠️ 获取 Pay Now DOM 信息失败：{e}"
        )

    # ========================================================
    # 第一种：force click
    # ========================================================

    try:

        log("🖱️ Pay Now：尝试 force=True...")

        await locator.click(
            force=True,
            timeout=10000
        )

        log("✅ Pay Now force=True 点击成功")

        await asyncio.sleep(5)

        return True

    except Exception as e:

        log(
            f"⚠️ Pay Now force 点击失败："
            f"{str(e)[:500]}"
        )

    # ========================================================
    # 第二种：DOM click
    # ========================================================

    try:

        log("🖱️ Pay Now：尝试 JavaScript element.click()...")

        await locator.evaluate(
            """
            element => {

                element.scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });

                element.click();
            }
            """
        )

        log("✅ Pay Now JavaScript click 成功")

        await asyncio.sleep(5)

        return True

    except Exception as e:

        log(
            f"⚠️ Pay Now JS click 失败："
            f"{str(e)[:500]}"
        )

    # ========================================================
    # 第三种：submit form
    #
    # 你的按钮明确是：
    #
    # <button type="submit">
    #
    # 所以这里直接提交它所属的 form。
    # ========================================================

    try:

        log("🖱️ Pay Now：尝试直接提交 form...")

        result = await locator.evaluate(
            """
            element => {

                const form = element.form;

                if (!form) {
                    return {
                        success: false,
                        reason: "no form"
                    };
                }

                form.requestSubmit(element);

                return {
                    success: true,
                    action: form.action,
                    method: form.method
                };
            }
            """
        )

        log(
            f"📨 Form submit 结果：{result}"
        )

        if result.get("success"):

            await asyncio.sleep(8)

            return True

    except Exception as e:

        log(
            f"⚠️ Pay Now form submit 失败："
            f"{str(e)[:500]}"
        )

    # ========================================================
    # 第四种：完整 MouseEvent
    # ========================================================

    try:

        log("🖱️ Pay Now：尝试完整 MouseEvent...")

        await locator.evaluate(
            """
            element => {

                element.scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });

                const events = [
                    'pointerover',
                    'mouseover',
                    'pointermove',
                    'mousemove',
                    'pointerdown',
                    'mousedown',
                    'pointerup',
                    'mouseup',
                    'click'
                ];

                for (const name of events) {

                    element.dispatchEvent(
                        new MouseEvent(name, {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            buttons: 1
                        })
                    );
                }
            }
            """
        )

        log("✅ Pay Now MouseEvent 已发送")

        await asyncio.sleep(8)

        return True

    except Exception as e:

        log(
            f"❌ Pay Now 所有点击方法均失败："
            f"{str(e)[:500]}"
        )

    return False


# ============================================================
# 检查付款 / 续期是否成功
# ============================================================

async def check_payment_success(page):

    log("🔎 检查付款/续期结果...")

    await asyncio.sleep(3)

    url = page.url

    log(f"📍 当前 URL：{url}")

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    if "/payment/" in url.lower():
        log("💳 当前已经进入 Payment 页面")
        return True

    # --------------------------------------------------------
    # 页面文字
    # --------------------------------------------------------

    try:

        text = await page.locator("body").inner_text(
            timeout=10000
        )

        lower = text.lower()

        success_words = [
            "payment successful",
            "payment completed",
            "invoice paid",
            "paid",
            "renewed",
            "renewal successful",
            "successfully renewed",
        ]

        for word in success_words:

            if word in lower:

                log(
                    f"✅ 检测到成功状态文字：{word}"
                )

                return True

    except Exception:
        pass

    return False


# ============================================================
# 完整续期
# ============================================================

async def renew_service(page):

    log("============================================================")
    log("🚀 开始 HidenCloud 续期")
    log("============================================================")

    log(f"📍 当前 URL：{page.url}")

    # --------------------------------------------------------
    # 点击 Renew
    # --------------------------------------------------------

    if not await click_renew(page):

        log("❌ Renew 点击失败")

        return False

    # --------------------------------------------------------
    # 等待 Invoice 状态
    # --------------------------------------------------------

    state, locator = await wait_invoice_state(
        page,
        timeout=30
    )

    # ========================================================
    # Create Invoice
    # ========================================================

    if state == "create_invoice":

        log("🎯 检测到 Create Invoice")

        ok = await click_create_invoice(
            page,
            locator
        )

        if not ok:

            log("❌ Create Invoice 点击失败")

            await screenshot(
                page,
                "hidencloud_create_invoice_failed.png"
            )

            return False

        # Create Invoice 后重新寻找 Pay Now

        log("🔎 Create Invoice 后重新寻找 Pay Now...")

        state2, pay_locator = await wait_invoice_state(
            page,
            timeout=30
        )

        if state2 != "pay_now":

            log(
                "⚠️ Create Invoice 后没有检测到 Pay Now"
            )

            await debug_buttons(page)

            await screenshot(
                page,
                "hidencloud_pay_now_not_found_after_invoice.png"
            )

            return False

        locator = pay_locator

    # ========================================================
    # Pay Now
    # ========================================================

    elif state == "pay_now":

        log("🎯 页面没有 Create Invoice，但已经出现 Pay Now")
        log("✅ 判断：Invoice 已经创建。")

    else:

        log("❌ 30 秒内没有找到 Create Invoice / Pay Now")

        await debug_buttons(page)

        await screenshot(
            page,
            "hidencloud_invoice_state_not_found.png"
        )

        return False

    # ========================================================
    # 点击 Pay Now
    # ========================================================

    log("🔎 检查 Pay Now...")

    pay_locator = await find_pay_now(page)

    if not pay_locator:

        log("❌ Pay Now 不存在")

        await debug_buttons(page)

        await screenshot(
            page,
            "hidencloud_pay_now_missing.png"
        )

        return False

    log("💳 检测到 Pay Now")

    before_url = page.url

    ok = await click_pay_now(
        page,
        pay_locator
    )

    if not ok:

        log("❌ Pay Now 点击最终失败")

        await screenshot(
            page,
            "hidencloud_pay_now_click_failed.png"
        )

        return False

    # --------------------------------------------------------
    # 等待支付页面/结果
    # --------------------------------------------------------

    log("⏳ Pay Now 点击完成，等待 HidenCloud 响应...")

    await asyncio.sleep(PAY_WAIT)

    await wait_cloudflare(
        page,
        timeout=30
    )

    after_url = page.url

    log(f"📍 点击后 URL：{after_url}")

    if after_url != before_url:

        log("🔄 检测到 URL 发生变化")

    # --------------------------------------------------------
    # 检查结果
    # --------------------------------------------------------

    success = await check_payment_success(
        page
    )

    if success:

        log("✅ 检测到付款/续期页面状态")

    else:

        log(
            "⚠️ 暂时没有检测到明确的付款成功文字"
        )

    return True


# ============================================================
# 主程序
# ============================================================

async def main():

    old_due_date = None
    new_due_date = None

    async with async_playwright() as p:

        log("🚀 启动 Chromium...")

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1920,1080",
        ]

        browser_options = {
            "headless": HEADLESS,
            "args": launch_args,
        }

        if PROXY_SERVER:

            log(
                f"🌐 使用代理：{PROXY_SERVER}"
            )

            browser_options["proxy"] = {
                "server": PROXY_SERVER
            }

        browser = await p.chromium.launch(
            **browser_options
        )

        context = await browser.new_context(
            viewport={
                "width": 1920,
                "height": 1080
            },
            screen={
                "width": 1920,
                "height": 1080
            },
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )

        # ----------------------------------------------------
        # Cookie
        # ----------------------------------------------------

        cookies = build_cookie()

        if cookies:

            await context.add_cookies(
                cookies
            )

            log("🍪 HidenCloud Cookie 已加载")

        page = await context.new_page()

        # ----------------------------------------------------
        # 自动接受 dialog
        # ----------------------------------------------------

        async def handle_dialog(dialog):

            log(
                f"⚠️ 检测到网页弹窗："
                f"{dialog.message}"
            )

            try:
                await dialog.accept()
                log("✅ 已接受网页弹窗")
            except Exception as e:
                log(
                    f"⚠️ 弹窗处理失败：{e}"
                )

        page.on(
            "dialog",
            handle_dialog
        )

        # ----------------------------------------------------
        # 监听新页面
        # ----------------------------------------------------

        def page_created(new_page):

            log(
                f"🆕 检测到新页面："
                f"{new_page.url}"
            )

        context.on(
            "page",
            page_created
        )

        # ====================================================
        # 打开服务器管理页
        # ====================================================

        log(
            f"🌐 打开：{SERVICE_URL}"
        )

        await page.goto(
            SERVICE_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await asyncio.sleep(3)

        await wait_cloudflare(
            page,
            timeout=30
        )

        log(
            f"📍 当前 URL：{page.url}"
        )

        # ====================================================
        # 登录检查
        # ====================================================

        body_text = ""

        try:

            body_text = await page.locator(
                "body"
            ).inner_text(timeout=10000)

        except Exception:
            pass

        if (
            "login" in page.url.lower()
            or "sign in" in body_text.lower()
        ):

            log("❌ Cookie 登录失败")

            await screenshot(
                page,
                "hidencloud_login_failed.png"
            )

            send_telegram(
                "❌ HidenCloud 自动续期失败\n"
                "原因：Cookie 登录失败"
            )

            await browser.close()

            raise RuntimeError(
                "HidenCloud Cookie 登录失败"
            )

        log("✅ Cookie 登录成功")

        # ====================================================
        # 获取旧 Due Date
        # ====================================================

        old_due_date = await get_due_date(
            page
        )

        log(
            f"📅 当前 Due Date："
            f"{old_due_date}"
        )

        # ====================================================
        # 续期
        # ====================================================

        success = await renew_service(
            page
        )

        if not success:

            log("❌ 续期流程失败")

            send_telegram(
                "❌ HidenCloud 自动续期失败\n"
                f"服务器：{SERVICE_ID}\n"
                f"Due Date：{old_due_date}"
            )

            await browser.close()

            raise RuntimeError(
                "HidenCloud 续期失败"
            )

        # ====================================================
        # 回服务器页面
        # ====================================================

        log("🔄 返回服务器管理页面...")

        try:

            await page.goto(
                SERVICE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

        except Exception as e:

            log(
                f"⚠️ 返回管理页面异常：{e}"
            )

        await asyncio.sleep(5)

        await wait_cloudflare(
            page,
            timeout=30
        )

        # ====================================================
        # 第一次检查
        # ====================================================

        new_due_date = await get_due_date(
            page
        )

        log(
            f"📅 当前 Due Date："
            f"{new_due_date}"
        )

        # ====================================================
        # 如果没有更新，等待
        # ====================================================

        if old_due_date == new_due_date:

            log(
                "⏳ Due Date 暂时没有变化"
            )

            log(
                "⏳ 等待 HidenCloud 更新 Due Date..."
            )

            for i in range(6):

                await asyncio.sleep(10)

                try:

                    await page.reload(
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                except Exception:
                    pass

                await wait_cloudflare(
                    page,
                    timeout=20
                )

                new_due_date = await get_due_date(
                    page
                )

                log(
                    f"🔄 第 {i + 1}/6 次检查："
                    f"{new_due_date}"
                )

                if new_due_date != old_due_date:
                    break

        # ====================================================
        # 最终结果
        # ====================================================

        log(
            f"📆 续期后到期时间："
            f"{new_due_date}"
        )

        if (
            new_due_date
            and old_due_date
            and new_due_date != old_due_date
        ):

            log("🎉 HidenCloud 续期成功！")

            message = (
                "✅ HidenCloud 自动续期成功\n\n"
                f"服务器：{SERVICE_ID}\n"
                f"原到期时间：{old_due_date}\n"
                f"新到期时间：{new_due_date}"
            )

            send_telegram(message)

        else:

            log("❌ Due Date 没有变化")

            log(
                f"旧日期：{old_due_date}"
            )

            log(
                f"新日期：{new_due_date}"
            )

            await screenshot(
                page,
                "hidencloud_due_date_not_changed.png"
            )

            # 保存 HTML，方便下一次精准分析
            try:

                with open(
                    "/tmp/hidencloud_debug.html",
                    "w",
                    encoding="utf-8"
                ) as f:

                    f.write(
                        await page.content()
                    )

                log(
                    "📄 HTML 已保存："
                    "/tmp/hidencloud_debug.html"
                )

            except Exception:
                pass

            send_telegram(
                "❌ HidenCloud 自动续期失败\n\n"
                f"服务器：{SERVICE_ID}\n"
                f"旧日期：{old_due_date}\n"
                f"新日期：{new_due_date}\n\n"
                "Pay Now 点击/付款状态可能未完成。"
            )

            await browser.close()

            raise RuntimeError(
                "Due Date 没有变化"
            )

        await browser.close()


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log("程序被手动停止")

    except Exception as e:

        log(
            f"❌ 程序异常：{e}"
        )

        traceback.print_exc()

        raise
