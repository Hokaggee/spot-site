async page => {
  const context=await page.context().browser().newContext();
  const test=await context.newPage(),base='http://127.0.0.1:8082';
  const assert=(value,message)=>{if(!value)throw new Error(message);};
  try{
    await test.goto(base+'/admin');
    await test.locator('#login-panel').waitFor({state:'visible'});
    assert(await test.locator('#workspace').isHidden(),'Editor must remain hidden before login');
    const denied=await context.request.get(base+'/api/admin/albums');
    assert(denied.status()===401,'Anonymous users cannot read the admin API');
    for(const path of ['/.spot-data/admin-auth.json','/auth.py','/manage_admin.py']){
      const response=await context.request.get(base+path);assert(response.status()===404,'Private server file must not be exposed: '+path);
    }
    await test.getByLabel('Логин',{exact:true}).fill('wrong-user');
    await test.getByLabel('Пароль',{exact:true}).fill('spot-qa-only-password');
    await test.getByRole('button',{name:'Войти',exact:true}).click();
    await test.getByText('Неверный логин или пароль.',{exact:true}).waitFor();
    assert(await test.locator('#workspace').isHidden(),'Correct password with incorrect username must not log in');
    await test.getByLabel('Логин',{exact:true}).fill('admin');
    await test.getByRole('button',{name:'Войти',exact:true}).click();
    await test.locator('#workspace').waitFor({state:'visible'});
    const cookies=await context.cookies();
    const session=cookies.find(c=>c.name==='spot_session');
    assert(session?.httpOnly&&session.sameSite==='Strict','Session cookie must be HttpOnly and SameSite Strict');
    assert((await context.request.get(base+'/api/admin/albums')).status()===200,'Authenticated user can use the editor');
    await test.getByRole('button',{name:'Выйти',exact:true}).click();
    await test.locator('#login-panel').waitFor({state:'visible'});
    assert((await context.request.get(base+'/api/admin/albums')).status()===401,'Logout revokes access');
    await test.setViewportSize({width:390,height:844});
    assert(await test.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile login has no horizontal overflow');
    return 'PASS: private credential/source files, anonymous denial, username+password login, secure session attributes, logout and mobile login';
  }finally{await context.close();}
}
