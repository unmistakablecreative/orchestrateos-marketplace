#!/usr/bin/env node
/**
 * render_infographic.js
 * Converts HTML infographic to PNG using Playwright
 * 
 * Usage: node render_infographic.js <input.html> <output.png>
 */

const { chromium } = require('playwright');
const path = require('path');

async function htmlToPng(htmlPath, outputPath) {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    
    // Set viewport to match our 1200px design
    await page.setViewportSize({ width: 1200, height: 2000 });
    
    // Load the HTML file
    const absolutePath = path.resolve(htmlPath);
    await page.goto(`file://${absolutePath}`);
    
    // Wait for fonts/images to load
    await page.waitForTimeout(500);
    
    // Get actual content height
    const bodyHeight = await page.evaluate(() => document.body.scrollHeight);
    
    // Resize viewport to fit content
    await page.setViewportSize({ width: 1200, height: bodyHeight });
    
    // Screenshot full page
    await page.screenshot({ 
        path: outputPath,
        fullPage: true,
        type: 'png'
    });
    
    await browser.close();
    console.log(`✓ Saved: ${outputPath}`);
}

// CLI usage
const args = process.argv.slice(2);
if (args.length < 2) {
    console.log('Usage: node render_infographic.js <input.html> <output.png>');
    process.exit(1);
}

htmlToPng(args[0], args[1]).catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
