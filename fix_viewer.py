import re
path = '/home/jmq/omniaide/backend/plugins/remote/backend/router.py'
with open(path, 'r') as f:
    content = f.read()

old_kd = "document.addEventListener('keydown',e=>{if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyDown',code:e.code});}});"
new_kd = "document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyDown',code:e.code});}});"
content = content.replace(old_kd, new_kd)

old_ku = "document.addEventListener('keyup',e=>{if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyUp',code:e.code});}});"
new_ku = "document.addEventListener('keyup',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyUp',code:e.code});}});"
content = content.replace(old_ku, new_ku)

with open(path, 'w') as f:
    f.write(content)
print('Fixed OK')
