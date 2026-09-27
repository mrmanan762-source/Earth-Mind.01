import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 390, "height": 844})

        # 1. Open Home Page
        await page.goto("http://127.0.0.1:5173/")
        await page.wait_for_selector("text=EarthMind से पूछें")
        await page.screenshot(path="/tmp/earthmind_home.png")
        print("Captured /tmp/earthmind_home.png")

        # 2. Click Primary Action: "EarthMind से पूछें"
        await page.click("text=EarthMind से पूछें")
        await page.wait_for_selector("text=24x7 कृषि विशेषज्ञ मार्गदर्शन")

        # 3. Click "+" button in assistant composer
        await page.click("button[aria-label='टूल्स खोलें']")
        await page.wait_for_selector("text=EarthMind टूल और सुविधाएं")
        await page.screenshot(path="/tmp/earthmind_assistant_plus_menu.png")
        print("Captured /tmp/earthmind_assistant_plus_menu.png")

        # 4. Click "अपनी फसल जाँचें"
        await page.click("text=अपनी फसल जाँचें")
        await page.wait_for_selector("text=नमूना फोटो का उपयोग करें")
        await page.click("text=धान फोटो 1")
        await page.click("text=फसल जाँच शुरू करें")
        await page.wait_for_selector("text=निदान पूर्ण (Analysis Complete)")
        await page.screenshot(path="/tmp/earthmind_crop_analysis_result.png")
        print("Captured /tmp/earthmind_crop_analysis_result.png")

        # 5. Go to Drone Scan via Assistant '+' menu
        await page.click("text=EarthMind से और पूछें")
        await page.click("button[aria-label='टूल्स खोलें']")
        await page.click("text=ड्रोन जाँचें")
        await page.wait_for_selector("text=ड्रोन स्कैन शुरू करें")
        await page.click("text=ड्रोन स्कैन शुरू करें")
        await page.wait_for_selector("text=ड्रोन स्कैन पूर्ण", timeout=10000)
        await page.screenshot(path="/tmp/earthmind_drone_scan_result.png")
        print("Captured /tmp/earthmind_drone_scan_result.png")

        # 6. Navigate to Fields using bottom nav
        nav_fields = page.locator("nav button:has-text('खेत')")
        await nav_fields.click()
        await page.wait_for_selector("text=मेरे खेत")
        await page.screenshot(path="/tmp/earthmind_fields.png")
        print("Captured /tmp/earthmind_fields.png")

        # 7. Navigate to Profile using bottom nav
        nav_profile = page.locator("nav button:has-text('प्रोफाइल')")
        await nav_profile.click()
        await page.wait_for_selector("text=रामकुमार पटेल")
        await page.screenshot(path="/tmp/earthmind_profile.png")
        print("Captured /tmp/earthmind_profile.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
