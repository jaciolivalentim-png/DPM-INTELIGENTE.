let csrfToken = "";
fetch("/api/session", {credentials:"same-origin"}).then(async r=>{if(!r.ok){location.href="/login";return;}const d=await r.json();csrfToken=d.csrf;window.currentRole=d.role; if(d.role!=="admin"){document.querySelectorAll("[data-page=equipe],[data-page=auditoria]").forEach(el=>el.hidden=true)}document.getElementById("loggedUser").textContent=d.username;}).catch(()=>location.href="/login");
document.getElementById("logoutButton").addEventListener("click",async()=>{await fetch("/logout",{method:"POST",headers:{"X-CSRF-Token":csrfToken},credentials:"same-origin"});location.href="/login";});
const state={analises:[],documentos:0,relatorios:0};
function navigate(id){document.querySelectorAll(".page").forEach(p=>p.classList.remove("active"));document.getElementById(id)?.classList.add("active");document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===id))}
document.querySelectorAll(".nav-item").forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.page)));
function selectArea(area){document.getElementById("assunto").value=area;navigate("analise")}
const fileInput=document.getElementById("protocolFile"), info=document.getElementById("fileInfo"), drop=document.getElementById("dropArea");
function showFile(file){if(!file){info.textContent="Nenhum arquivo selecionado.";return}let ext=file.name.split(".").pop().toLowerCase();if(!["pdf","zip"].includes(ext)){info.textContent="Formato não permitido.";fileInput.value="";return}info.textContent=`${file.name} | ${(file.size/1024/1024).toFixed(2)} MB`}
fileInput.addEventListener("change",()=>showFile(fileInput.files[0]));
["dragenter","dragover"].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add("dragging")}));
["dragleave","drop"].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove("dragging")}));
drop.addEventListener("drop",e=>{const f=e.dataTransfer.files[0];if(!f)return;const dt=new DataTransfer();dt.items.add(f);fileInput.files=dt.files;showFile(f)});
document.getElementById("analyzeButton").addEventListener("click",async()=>{const numero=document.getElementById("numero").value.trim(),assunto=document.getElementById("assunto").value,arquivo=fileInput.files[0],feedback=document.getElementById("feedback"),btn=document.getElementById("analyzeButton");if(!arquivo){feedback.textContent="Selecione um arquivo PDF ou ZIP.";return}feedback.textContent="Processando documento...";btn.disabled=true;const fd=new FormData();fd.append("protocol",numero);fd.append("subject",assunto);fd.append("observations",document.getElementById("observacoes").value);fd.append("file",arquivo);try{const res=await fetch("/api/analyze",{method:"POST",body:fd,headers:{"X-CSRF-Token":csrfToken},credentials:"same-origin"});const data=await res.json();if(!res.ok)throw new Error(data.error||"Falha na análise.");showResult(data);state.analises.unshift({numero:numero||"Não informado",assunto:assunto||"Não informado",arquivo:arquivo.name,data:new Date().toLocaleString("pt-BR")});state.documentos+=data.total_documents;state.relatorios++;updateDashboard();feedback.textContent="Análise concluída com sucesso."}catch(err){feedback.textContent="Erro: "+err.message}finally{btn.disabled=false}});
function showResult(d){
  document.getElementById("resultDocuments").textContent=d.total_documents;
  document.getElementById("resultPages").textContent=d.total_pages;
  document.getElementById("resultSummary").textContent=d.summary||"Não foi possível produzir resumo textual.";
  document.getElementById("resultProtocol").textContent=d.protocol||"Não informado";
  document.getElementById("resultSubject").textContent=d.subject||"Não informado";
  document.getElementById("resultFiles").textContent=(d.documents||[]).map(x=>x.name||"Arquivo sem nome").join(", ")||"Não informado";
  document.getElementById("resultAnalysis").textContent=d.preliminary_analysis||"Não disponível";
  document.getElementById("resultResponse").textContent=d.suggested_response||"Não disponível";
  const list=document.getElementById("resultAttention");list.replaceChildren();
  (d.attention_points||[]).forEach(p=>{const li=document.createElement("li");li.textContent=p;list.appendChild(li)});
  const topics=document.getElementById("resultTopics");topics.replaceChildren();
  (d.identified_topics||[]).forEach(t=>{const li=document.createElement("li");li.textContent=t;topics.appendChild(li)});
  if(!topics.children.length){const li=document.createElement("li");li.textContent="Nenhum tema classificado automaticamente.";topics.appendChild(li)}
  const evidence=document.getElementById("resultEvidence");evidence.replaceChildren();
  (d.evidence||[]).forEach(e=>{const item=document.createElement("div");item.className="evidence-item";const h=document.createElement("strong");h.textContent=e.topic;const p=document.createElement("p");p.textContent=e.excerpt;item.append(h,p);evidence.appendChild(item)});
  if(!evidence.children.length){const p=document.createElement("p");p.textContent="Nenhum trecho específico identificado pelas regras atuais.";evidence.appendChild(p)}
  document.getElementById("resultLimitations").textContent=d.limitations||"";
  const panel=document.getElementById("resultPanel");panel.classList.remove("hidden");panel.scrollIntoView({behavior:"smooth"});
}
function updateDashboard(){document.getElementById("totalAnalises").textContent=state.analises.length;document.getElementById("totalDocumentos").textContent=state.documentos;document.getElementById("totalRelatorios").textContent=state.relatorios;const h=document.getElementById("historyList");h.replaceChildren();if(!state.analises.length){h.textContent="Nenhuma análise registrada.";return}state.analises.forEach(i=>{const el=document.createElement("div");el.className="history-item";const strong=document.createElement("strong");strong.textContent="Protocolo: "+i.numero;const p=document.createElement("p");p.textContent=[i.assunto,i.arquivo,i.data].join(" | ");el.append(strong,p);h.appendChild(el)})}
// Imprime apenas a área do relatório usando a função de impressão do navegador.
document.getElementById("exportReport").addEventListener("click",()=>window.print());

// Administração de usuários (acesso autorizado pelo backend).
async function teamRequest(url,options={}){
 const res=await fetch(url,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken,...(options.headers||{})}});
 const data=await res.json();if(!res.ok)throw Error(data.error||'Operação não concluída.');return data;
}
async function loadTeam(){if(window.currentRole!=='admin')return;const area=document.getElementById('teamUsers');try{
 const data=await teamRequest('/api/users');area.replaceChildren();
 for(const u of data.users){const row=document.createElement('div');row.className='team-user';const name=document.createElement('strong');name.textContent=u.username+' ('+(u.role==='admin'?'Administrador':'Analista')+') — '+(u.active?'Ativo':'Inativo');row.appendChild(name);
 const role=document.createElement('button');role.type='button';role.textContent=u.role==='admin'?'Tornar analista':'Tornar administrador';role.disabled=u.username===document.getElementById('loggedUser').textContent;role.addEventListener('click',async()=>{if(!confirm('Alterar a permissão desta conta?'))return;try{await teamRequest('/api/users/'+u.id,{method:'PATCH',body:JSON.stringify({role:u.role==='admin'?'analyst':'admin'})});loadTeam()}catch(e){alert(e.message)}});
 const active=document.createElement('button');active.type='button';active.textContent=u.active?'Desativar':'Ativar';active.disabled=role.disabled;active.addEventListener('click',async()=>{if(!confirm('Alterar o status desta conta?'))return;try{await teamRequest('/api/users/'+u.id,{method:'PATCH',body:JSON.stringify({active:!u.active})});loadTeam()}catch(e){alert(e.message)}});
 const reset=document.createElement('button');reset.type='button';reset.textContent='Redefinir senha';reset.addEventListener('click',async()=>{const password=prompt('Digite a nova senha (mínimo 12 caracteres):');if(password===null)return;try{await teamRequest('/api/users/'+u.id,{method:'PATCH',body:JSON.stringify({password})});alert('Senha atualizada.')}catch(e){alert(e.message)}});
 row.append(role,active,reset);area.appendChild(row)}
 }catch(e){area.textContent=e.message}}
document.getElementById('userForm').addEventListener('submit',async e=>{e.preventDefault();const feedback=document.getElementById('teamFeedback');try{await teamRequest('/api/users',{method:'POST',body:JSON.stringify({username:document.getElementById('newUsername').value,password:document.getElementById('newPassword').value,role:document.getElementById('newRole').value})});feedback.textContent='Usuário criado com sucesso.';e.target.reset();loadTeam()}catch(err){feedback.textContent=err.message}});
async function loadAudit(){if(window.currentRole!=='admin')return;const area=document.getElementById('auditEvents');try{const data=await teamRequest('/api/audit');area.replaceChildren();for(const e of data.events){const p=document.createElement('p');p.textContent=new Date(e.date).toLocaleString('pt-BR')+' — '+(e.actor||'Sistema')+' — '+e.action;area.appendChild(p)}if(!data.events.length)area.textContent='Nenhuma alteração registrada.'}catch(e){area.textContent=e.message}}
document.querySelector('[data-page="equipe"]').addEventListener('click',loadTeam);
document.querySelector('[data-page="auditoria"]').addEventListener('click',loadAudit);
