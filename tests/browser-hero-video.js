async page => {
  const preview = await page.context().newPage();
  try {
    await preview.emulateMedia({reducedMotion:'no-preference'});
    // The opening video should start even while application code is unavailable.
    await preview.route('**/app.js', route => route.fulfill({contentType:'text/javascript',body:''}));
    await preview.goto('http://127.0.0.1:8081/');
    await preview.waitForFunction(() => {
      const video = document.querySelector('#hero-video');
      return video && !video.paused && video.currentTime > .1;
    }, null, {timeout:4000});
    await preview.unroute('**/app.js');
    await preview.reload();
    await preview.waitForFunction(() => !document.querySelector('#hero-video').paused);
    await preview.locator('#place').scrollIntoViewIfNeeded();
    await preview.waitForFunction(() => document.querySelector('#hero-video').paused);
    await preview.locator('.footer-top').click();
    await preview.waitForFunction(() => scrollY < 10 && !document.querySelector('#hero-video').paused);
    await preview.locator('.video-toggle').click();
    await preview.waitForFunction(() => document.querySelector('#hero-video').paused);
    await preview.locator('.video-toggle').click();
    await preview.waitForFunction(() => !document.querySelector('#hero-video').paused);
    await preview.emulateMedia({reducedMotion:'reduce'});
    await preview.waitForFunction(() => document.querySelector('#hero-video').paused);
    return 'PASS: native hero autoplay, return-to-top resumes, pause/play controls and reduced motion';
  } finally { await preview.close({runBeforeUnload:false}); }
}
