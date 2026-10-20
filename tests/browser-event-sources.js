async page => {
  const preview = await page.context().newPage();
  const yandex = 'https://afisha.yandex.ru/blagoveshchensk/concert/kitana-tour';
  try {
    await preview.route('**/api/events', route => route.fulfill({json:{events:[
      {title:'Kitana', starts_at:'2026-11-15T20:00:00+09:00', url:yandex, poster:'', category:'Концерт', price:'от 2000 ₽', source:'yandex', source_name:'Яндекс Афиша'},
      {title:'Проверка Qtickets', starts_at:'2026-12-01T20:00:00+09:00', url:'https://blagoveshensk.qtickets.events/123-test', poster:'', category:'Концерт', price:'', source:'qtickets', source_name:'Qtickets'}
    ],updated_at:new Date().toISOString(),sources:[
      {id:'qtickets',name:'Qtickets',updated_at:new Date().toISOString(),stale:false},
      {id:'yandex',name:'Яндекс Афиша',updated_at:new Date().toISOString(),stale:true}
    ]}}));
    await preview.goto('http://127.0.0.1:8081/#events');
    const ya = preview.getByRole('link',{name:'Купить билет: Kitana — Яндекс Афиша',exact:true});
    await ya.waitFor({timeout:2500});
    if (await ya.getAttribute('href') !== yandex) throw new Error('Yandex ticket URL is wrong');
    const card = preview.locator('.event').filter({has:preview.getByRole('heading',{name:'Kitana',exact:true})});
    if (!(await card.innerText()).includes('Билеты: Яндекс Афиша')) throw new Error('Seller is not visible on the card');
    if (!(await preview.locator('#events-status').innerText()).includes('Яндекс Афиша')) throw new Error('Source state missing');
    await preview.getByRole('link',{name:'Купить билет: Проверка Qtickets — Qtickets',exact:true}).waitFor();
    for (const width of [320,390,1440]) {
      await preview.setViewportSize({width,height:900});
      if (!await preview.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)) throw new Error(`Overflow at ${width}px`);
    }
    return 'PASS: Yandex and Qtickets ticket destinations, visible seller names, independent source status and responsive layout';
  } finally { await preview.close({runBeforeUnload:false}); }
}
