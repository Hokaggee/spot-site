async page => {
  const preview = await page.context().newPage();
  try {
    await preview.goto('http://127.0.0.1:8081/#events');
    await preview.locator('.event-poster').first().waitFor();
    await preview.locator('.event-poster').evaluateAll(images => images.forEach(image => image.loading = 'eager'));
    await preview.waitForFunction(() => [...document.querySelectorAll('.event-poster')].every(image => image.complete && image.naturalWidth));
    for (const width of [390, 1440]) {
      await preview.setViewportSize({width, height:900});
      const cropped = await preview.locator('.event-poster').evaluateAll(images => images.filter(image =>
        Math.abs(image.clientWidth / image.clientHeight - image.naturalWidth / image.naturalHeight) > .01
      ).map(image => image.alt));
      if (cropped.length) throw new Error(`Posters cropped at ${width}px: ${cropped.join(', ')}`);
    }
    const fight = preview.locator('.event').filter({has:preview.getByRole('heading',{name:'Бои на СПОТЕ',exact:true})}).locator('img');
    if (await fight.evaluate(image => image.naturalWidth) < 720) throw new Error('Fight poster is still a low-resolution thumbnail');
    return 'PASS: all posters retain full proportions on mobile/desktop; fight poster loads at high resolution';
  } finally { await preview.close({runBeforeUnload:false}); }
}
