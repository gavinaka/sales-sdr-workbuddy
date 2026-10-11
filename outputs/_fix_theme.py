path='C:/Users/杨杨/Desktop/销售SDR/outputs/_lead_dashboard_v4.js'
text=open(path,'r',encoding='utf-8').read()
old="if(localStorage.getItem('lead-theme'))setTheme(localStorage.getItem('lead-theme'));\r\nelse if(window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches)setTheme('dark');"
new="try{\r\n  if(localStorage.getItem('lead-theme'))setTheme(localStorage.getItem('lead-theme'));\r\n  else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches)setTheme('dark');\r\n}catch(e){}"
print('old found:', old in text)
if old in text:
    text=text.replace(old,new)
    open(path,'w',encoding='utf-8').write(text)
    print('replaced')
else:
    print('not found')
