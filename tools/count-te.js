const fs = require('fs');
const s = fs.readFileSync('E:/02_Installers/DailyApps/Modex-MH-Agent-RE/beauty/NewWorkflow-Ld6TEJjT.pretty.js', 'utf8');
const comp = [...new Set(s.match(/value:`comp_[a-z_0-9]+`/g) || [])];
console.log('comp_* templates:', comp.length);
console.log(comp.map(x => x.slice(7, -1)).join(', '));
console.log('academic entries:', (s.match(/category:`academic`/g) || []).length);
console.log('research entries:', (s.match(/category:`research`/g) || []).length);
const all = [...new Set(s.match(/value:`[a-z_0-9-]+`/g) || [])];
console.log('all value: literals', all.length);
