let csrfToken = "";
fetch("/api/session", {credentials:"same-origin"}).then(async r=>{if(!r.ok){location.href="/login";return;}const d=await r.json();csrfToken=d.csrf;window.currentRole=d.role; if(d.role!=="admin"){document.querySelectorAll("[data-page=equipe],[data-page=auditoria],[data-page=produtividade]").forEach(el=>el.hidden=true)}document.getElementById("loggedUser").textContent=d.username;if(d.role==="admin")loadProductivity();}).catch(()=>location.href="/login");
document.getElementById("logoutButton").addEventListener("click",async()=>{await fetch("/logout",{method:"POST",headers:{"X-CSRF-Token":csrfToken},credentials:"same-origin"});location.href="/login";});
const state={analises:[],documentos:0,relatorios:0};
function navigate(id){document.querySelectorAll(".page").forEach(p=>p.classList.remove("active"));document.getElementById(id)?.classList.add("active");document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===id))}
document.querySelectorAll(".nav-item").forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.page)));
function selectArea(area){document.getElementById("assunto").value=area;navigate("analise")}
const fileInput=document.getElementById("protocolFile"), info=document.getElementById("fileInfo"), drop=document.getElementById("dropArea");
function showFile(file){if(!file){info.textContent="Nenhum arquivo selecionado.";return}let ext=file.name.split(".").pop().toLowerCase();if(!["pdf","zip","jpg","jpeg","png"].includes(ext)){info.textContent="Formato não permitido.";fileInput.value="";return}info.textContent=`${file.name} | ${(file.size/1024/1024).toFixed(2)} MB`}
fileInput.addEventListener("change",()=>showFile(fileInput.files[0]));
["dragenter","dragover"].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add("dragging")}));
["dragleave","drop"].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove("dragging")}));
drop.addEventListener("drop",e=>{const f=e.dataTransfer.files[0];if(!f)return;const dt=new DataTransfer();dt.items.add(f);fileInput.files=dt.files;showFile(f)});
document.getElementById("analyzeButton").addEventListener("click",async()=>{
 const numero=document.getElementById("numero").value.trim(),assunto=document.getElementById("assunto").value;
 const arquivo=fileInput.files[0],feedback=document.getElementById("feedback"),btn=document.getElementById("analyzeButton");
 const panel=document.getElementById("progressPanel"),bar=document.getElementById("progressBar"),label=document.getElementById("progressLabel");
 if(!arquivo){feedback.textContent="Selecione um arquivo PDF, ZIP, JPG ou PNG.";return}
 if(arquivo.size>100*1024*1024){feedback.textContent="O arquivo excede o limite de 100 MB.";return}
 btn.disabled=true;panel.classList.remove("hidden");bar.value=0;bar.removeAttribute("max");label.textContent="Enviando arquivo...";feedback.textContent="";
 const fd=new FormData();fd.append("protocol",numero);fd.append("subject",assunto);
 fd.append("observations",document.getElementById("observacoes").value);fd.append("draft_type",document.getElementById("draftType").value);fd.append("file",arquivo);
 try{
  const res=await fetch("/api/analyze/start",{method:"POST",body:fd,headers:{"X-CSRF-Token":csrfToken},credentials:"same-origin"});
  const data=await res.json();if(!res.ok)throw Error(data.error||"Não foi possível iniciar a análise.");
  const id=data.job_id;let done=false;
  while(!done){
   await new Promise(resolve=>setTimeout(resolve,1500));
   const r=await fetch("/api/analyze/progress/"+encodeURIComponent(id),{credentials:"same-origin"});
   if(!r.ok)throw Error("Não foi possível consultar o progresso. Faça login novamente se necessário.");
   const p=await r.json();
   if(p.total>0){bar.max=p.total;bar.value=p.page;label.textContent=`${p.stage} — ${p.page} de ${p.total} páginas (${Math.round(100*p.page/p.total)}%)`;}
   else {bar.removeAttribute("max");label.textContent=p.stage||"Processando...";}
   if(p.status==="failed"||p.status==="interrupted")throw Error(p.stage||"Análise interrompida.");
   if(p.status==="completed")done=true;
  }
  const response=await fetch("/api/analyze/result/"+encodeURIComponent(id),{credentials:"same-origin"});
  const result=await response.json();if(!response.ok)throw Error(result.error||"Resultado indisponível.");
  showResult(result);await loadHistory();feedback.textContent="Análise concluída com sucesso.";
  bar.max=100;bar.value=100;label.textContent="100% — análise concluída";
 }catch(err){feedback.textContent="Erro: "+err.message;label.textContent="Processamento não concluído.";}
 finally{btn.disabled=false}
});

let originalDraft = "";
function showResult(d){
  document.getElementById("resultDocuments").textContent=d.total_documents;
  document.getElementById("resultPages").textContent=d.total_pages;
  document.getElementById("resultSummary").textContent=d.summary||"Não foi possível produzir resumo textual.";
  document.getElementById("resultProtocol").textContent=d.protocol||"Não informado";
  document.getElementById("resultSubject").textContent=d.subject||"Não informado";
  document.getElementById("resultFiles").textContent=(d.documents||[]).map(x=>x.name||"Arquivo sem nome").join(", ")||"Não informado";
  const review=d.procedural_review||{};
  const section=document.getElementById("proceduralSection");
  const events=review.events||[];
  section.hidden=!events.length && !d.technical_conclusion;
  const timeline=document.getElementById("proceduralTimeline");timeline.replaceChildren();
  events.forEach(e=>{
    const tr=document.createElement("tr");
    [e.date||"Não informada",e.type||"Evento",e.page?`p. ${e.page}`:"Conferir"].forEach(v=>{
      const td=document.createElement("td");td.textContent=v;tr.appendChild(td);
    });timeline.appendChild(tr);
  });
  const comparison=review.deadline_comparison;
  document.getElementById("proceduralDelay").textContent=comparison&&comparison.days>0
    ?`Atraso aritmético aparente: ${comparison.days} dia(s) entre ${comparison.deadline} e ${comparison.filed}. Confirmar contagem legal e expediente.`
    :"Não há cálculo conclusivo de prazo. Conferir os marcos no processo original.";
  for(const [id,items] of [["proceduralClaims",review.claims||[]],["proceduralMedical",review.medical||[]]]){
    const ul=document.getElementById(id);ul.replaceChildren();
    items.slice(0,5).forEach(item=>{const li=document.createElement("li");li.textContent=`Página ${item.page}: ${item.excerpt}`;ul.appendChild(li)});
    if(!ul.children.length){const li=document.createElement("li");li.textContent="Não identificado de forma confiável; conferir documento original.";ul.appendChild(li)}
  }
  document.getElementById("technicalConclusion").textContent=d.technical_conclusion||"Conferência humana necessária.";
  const examplePages=review.preexisting_output_pages||[];
  document.getElementById("preexistingNotice").textContent=examplePages.length
    ?`Atenção: as páginas ${examplePages.join(", ")} já contêm exemplos de relatório ou minuta. Eles não são uma análise independente do sistema.`:"";
  document.getElementById("resultAnalysis").textContent=d.preliminary_analysis||"Não disponível";
  originalDraft=d.suggested_response||"Não disponível";
  document.getElementById("resultResponse").textContent=originalDraft;
  document.getElementById("draftStatus").textContent="Minuta pronta para revisão.";
  resetLocalReview();
  const list=document.getElementById("resultAttention");list.replaceChildren();
  (d.attention_points||[]).forEach(p=>{const li=document.createElement("li");li.textContent=p;list.appendChild(li)});
  const topics=document.getElementById("resultTopics");topics.replaceChildren();
  (d.identified_topics||[]).forEach(t=>{const li=document.createElement("li");li.textContent=t;topics.appendChild(li)});
  if(!topics.children.length){const li=document.createElement("li");li.textContent="Nenhum tema classificado automaticamente.";topics.appendChild(li)}
  const evidence=document.getElementById("resultEvidence");evidence.replaceChildren();
  (d.evidence||[]).forEach(e=>{const item=document.createElement("div");item.className="evidence-item";const h=document.createElement("strong");h.textContent=e.topic;const p=document.createElement("p");p.textContent=e.excerpt;item.append(h,p);evidence.appendChild(item)});
  if(!evidence.children.length){const p=document.createElement("p");p.textContent="Nenhum trecho específico identificado pelas regras atuais.";evidence.appendChild(p)}
  const ocrBox=document.getElementById("resultOcrDiagnostics");ocrBox.replaceChildren();
  const ocr=d.ocr_diagnostics||{};
  const status=document.createElement("p");
  status.textContent=`Páginas submetidas ao OCR: ${ocr.attempted_pages||0}; com texto reconhecido: ${ocr.text_pages||0}; caracteres extraídos: ${ocr.characters||0}.`;
  ocrBox.appendChild(status);
  (ocr.pages||[]).forEach(page=>{
    const item=document.createElement("div");item.className="evidence-item";
    const heading=document.createElement("strong");heading.textContent=`Página ${page.page} — ${page.characters} caracteres`;
    const preview=document.createElement("p");preview.textContent=page.preview||"Sem prévia";
    item.append(heading,preview);ocrBox.appendChild(item);
  });
  if((ocr.attempted_pages||0)>0 && !(ocr.text_pages||0)){
    const warning=document.createElement("p");warning.textContent="Atenção: nenhuma página submetida ao OCR produziu texto. Análise com limitações.";ocrBox.appendChild(warning);
  }
  document.getElementById("resultLimitations").textContent=d.limitations||"";
  const panel=document.getElementById("resultPanel");panel.classList.remove("hidden");panel.scrollIntoView({behavior:"smooth"});
}
let historyView = 'active';
async function historyAction(url,method,body){
 const res=await fetch(url,{method,credentials:'same-origin',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
 const data=await res.json();if(!res.ok)throw Error(data.error||'Não foi possível atualizar o registro.');return data;
}
async function loadHistory(){
 const area=document.getElementById('historyList');
 try {
  const res=await fetch('/api/history?view='+encodeURIComponent(historyView),{credentials:'same-origin'});
  const data=await res.json();if(!res.ok)throw Error(data.error||'Falha ao carregar histórico');
  area.replaceChildren();
  for(const i of data.items){
   const el=document.createElement('div');el.className='history-item';
   const strong=document.createElement('strong');strong.textContent='Registro #'+i.id+' — '+(i.protocol_label||'Sem identificador');
   const desc=document.createElement('p');desc.textContent=i.username+' | '+new Date(i.created_at).toLocaleString('pt-BR')+' | '+i.document_count+' documento(s) | '+i.page_count+' página(s)'+(i.archived?' | Arquivado':'');
   const actions=document.createElement('div');actions.className='history-actions';
   const archive=document.createElement('button');archive.type='button';archive.textContent=i.archived?'Restaurar':'Arquivar';
   archive.addEventListener('click',async()=>{try{archive.disabled=true;await historyAction('/api/history/'+i.id+'/archive','PATCH',{archived:!i.archived});await loadHistory()}catch(e){alert(e.message);archive.disabled=false}});
   actions.appendChild(archive);
   if(window.currentRole==='admin'){
    const del=document.createElement('button');del.type='button';del.className='danger-action';del.textContent='Excluir';
    del.addEventListener('click',async()=>{
     if(!confirm('Excluir PERMANENTEMENTE o registro #'+i.id+'? Esta ação não pode ser desfeita.'))return;
     try{del.disabled=true;await historyAction('/api/history/'+i.id,'DELETE');await loadHistory();await loadProductivity()}catch(e){alert(e.message);del.disabled=false}
    });actions.appendChild(del);
   }
   el.append(strong,desc,actions);area.appendChild(el);
  }
  if(!data.items.length)area.textContent='Nenhum registro nesta categoria.';
  document.getElementById('totalAnalises').textContent=data.items.length;
  document.getElementById('totalDocumentos').textContent=data.items.reduce((sum,i)=>sum+i.document_count,0);
  document.getElementById('totalRelatorios').textContent=data.items.length;
 }catch(e){area.textContent='Erro: '+e.message;}
}

async function loadProductivity(){
 if(window.currentRole!=='admin')return;
 const area=document.getElementById('prodUsers');
 try{
  const res=await fetch('/api/productivity',{credentials:'same-origin'});
  const d=await res.json();if(!res.ok)throw Error(d.error||'Falha ao carregar produtividade');
  document.getElementById('prodTotal').textContent=d.totals.analyses;
  document.getElementById('prodToday').textContent=d.totals.today;
  document.getElementById('prodDocs').textContent=d.totals.documents;
  document.getElementById('totalAnalises').textContent=d.totals.analyses;
  document.getElementById('totalDocumentos').textContent=d.totals.documents;
  document.getElementById('totalRelatorios').textContent=d.totals.analyses;
  area.replaceChildren();
  for(const u of d.users){const row=document.createElement('div');row.className='history-item';row.textContent=u.username+' — '+u.analyses+' análises no total | '+u.today+' hoje';area.appendChild(row);}
  if(!d.users.length)area.textContent='Nenhum usuário encontrado.';
 }catch(e){area.textContent='Erro: '+e.message;}
}
document.getElementById('historyView').addEventListener('change',e=>{historyView=e.target.value;loadHistory()});
document.getElementById('refreshHistory').addEventListener('click',loadHistory);
document.querySelector('[data-page="historico"]').addEventListener('click',loadHistory);
document.querySelector('[data-page="produtividade"]').addEventListener('click',loadProductivity);
loadHistory();
// Conferência apenas nesta sessão de tela; NÃO é aprovação institucional.
const reviewChecks = [...document.querySelectorAll('.review-check')];
const reviewButton = document.getElementById('markReviewed');
const reviewStatus = document.getElementById('reviewStatus');
function resetLocalReview(){
  reviewChecks.forEach(c => c.checked = false);
  reviewButton.disabled = true;
  reviewStatus.textContent = 'Pendente de conferência.';
}
reviewChecks.forEach(c => c.addEventListener('change', () => {
  reviewButton.disabled = !reviewChecks.every(x => x.checked);
  reviewStatus.textContent = 'Pendente de conferência.';
}));
reviewButton.addEventListener('click', () => {
  if (!reviewChecks.every(c => c.checked)) return;
  reviewStatus.textContent = 'Conferência local concluída — sem aprovação oficial ou registro no servidor.';
});
// O editor usa apenas texto, inclusive quando o usuário cola conteúdo externo.
const draftEditor=document.getElementById("resultResponse");
draftEditor.addEventListener("paste",event=>{
  event.preventDefault();
  const plain=(event.clipboardData||window.clipboardData).getData("text/plain");
  const selection=window.getSelection();
  if(!selection||!selection.rangeCount)return;
  const range=selection.getRangeAt(0);
  if(!draftEditor.contains(range.commonAncestorContainer))return;
  range.deleteContents();
  const node=document.createTextNode(plain);
  range.insertNode(node);
  range.setStartAfter(node);range.collapse(true);
  selection.removeAllRanges();selection.addRange(range);
});
draftEditor.addEventListener("input",()=>{document.getElementById("draftStatus").textContent="Minuta editada nesta tela (não salva no servidor).";resetLocalReview();});
document.getElementById("resetDraft").addEventListener("click",()=>{
  if(draftEditor.innerText.trim()!==originalDraft.trim()&&!confirm("Descartar suas edições e restaurar a minuta original?"))return;
  draftEditor.textContent=originalDraft;
  resetLocalReview();
  document.getElementById("draftStatus").textContent="Minuta original restaurada.";
});
document.getElementById("copyDraft").addEventListener("click",async()=>{
  try{await navigator.clipboard.writeText(draftEditor.innerText);document.getElementById("draftStatus").textContent="Minuta copiada."}
  catch(e){document.getElementById("draftStatus").textContent="Não foi possível copiar automaticamente. Selecione o texto e use Ctrl+C."}
});
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
async function loadAuditAnalyses(){
 if(window.currentRole!=='admin')return;
 const area=document.getElementById('auditAnalyses');
 try{
  const res=await fetch('/api/audit/analyses',{credentials:'same-origin'});
  if(!res.ok)throw new Error('Não foi possível consultar as análises.');
  const data=await res.json();area.replaceChildren();
  for(const a of data.analyses){
   const item=document.createElement('div');item.className='history-item';
   const date=new Date(a.date).toLocaleString('pt-BR');
   const ocr=a.ocr_attempted ? a.ocr_read+'/'+a.ocr_attempted+' páginas OCR; '+a.ocr_characters+' caracteres' : 'Sem métricas OCR registradas';
   item.textContent=date+' — '+a.actor+' — Protocolo: '+(a.protocol||'não informado')+
    ' — '+a.documents+' arquivo(s), '+a.pages+' página(s) — '+ocr+
    ' — Resultado: '+a.status+' — Revisão: '+a.review_status;
   area.appendChild(item);
  }
  if(!data.analyses.length)area.textContent='Nenhuma análise registrada.';
 }catch(e){area.textContent=e.message}
}
document.querySelector('[data-page="auditoria"]').addEventListener('click',()=>{loadAudit();loadAuditAnalyses()});


// Base normativa: catálogo de consulta. Referências locais não equivalem a normas validadas.
const NORMA_OFFICIAL = [{
 title:"Regulamentos — Saúde do Servidor (SAS/SEAP)",category:"Portal oficial",
 subject:"Página oficial de regulamentos, legislação e documentos de referência da Saúde do Servidor do Paraná.",
 url:"https://www.administracao.pr.gov.br/SAS/Pagina/Regulamentos",official:true
}];
const NORMA_STORAGE_KEY="dpm_normas_referencias_locais_v1";
function normaSaved(){try{const data=JSON.parse(localStorage.getItem(NORMA_STORAGE_KEY)||"[]");return Array.isArray(data)?data.filter(x=>x&&typeof x.title==="string"&&typeof x.url==="string"):[]}catch{return []}}
function normaValidUrl(value){try{const url=new URL(value);return url.protocol==="https:"&&!!url.hostname}catch{return false}}
function normaRender(){
 const list=document.getElementById("normaList");if(!list)return;
 const term=document.getElementById("normaSearch").value.trim().toLocaleLowerCase("pt-BR");
 const cat=document.getElementById("normaCategory").value;
 const items=[...NORMA_OFFICIAL,...normaSaved()].filter(n=>(!cat||n.category===cat)&&[n.title,n.subject,n.category].join(" ").toLocaleLowerCase("pt-BR").includes(term));
 list.replaceChildren();document.getElementById("normaCount").textContent=`${items.length} referência(s) encontrada(s)`;
 if(!items.length){const p=document.createElement("p");p.textContent="Nenhuma referência encontrada.";list.append(p);return}
 for(const n of items){
  const item=document.createElement("article");item.className="norma-item";
  const title=document.createElement("h3");title.textContent=n.title;
  const meta=document.createElement("p");meta.className="norma-meta";meta.textContent=n.category+" • "+(n.official?"Fonte institucional — verificar atualizações":"Cadastro local — não validado");
  const desc=document.createElement("p");desc.textContent=n.subject||"Sem descrição informada.";
  const actions=document.createElement("div");actions.className="norma-actions";
  if(normaValidUrl(n.url)){const a=document.createElement("a");a.href=n.url;a.target="_blank";a.rel="noopener noreferrer";a.textContent="Consultar fonte ↗";actions.append(a)}
  if(!n.official){const btn=document.createElement("button");btn.type="button";btn.textContent="Remover deste navegador";btn.addEventListener("click",()=>{if(!confirm("Remover esta referência local?"))return;localStorage.setItem(NORMA_STORAGE_KEY,JSON.stringify(normaSaved().filter(x=>x.id!==n.id)));normaRender()});actions.append(btn)}
  item.append(title,meta,desc,actions);list.append(item)
 }
}
document.getElementById("normaSearch")?.addEventListener("input",normaRender);
document.getElementById("normaCategory")?.addEventListener("change",normaRender);
document.getElementById("normaForm")?.addEventListener("submit",e=>{
 e.preventDefault();const feedback=document.getElementById("normaFeedback");
 const title=document.getElementById("normaTitle").value.trim(),category=document.getElementById("normaNewCategory").value,subject=document.getElementById("normaSubject").value.trim(),url=document.getElementById("normaUrl").value.trim();
 if(!title||!normaValidUrl(url)){feedback.textContent="Informe um título e um endereço HTTPS válido.";return}
 try{const entries=normaSaved();entries.push({id:Date.now()+"-"+Math.random().toString(36).slice(2),title,category,subject,url,official:false});localStorage.setItem(NORMA_STORAGE_KEY,JSON.stringify(entries));e.target.reset();feedback.textContent="Referência salva somente neste navegador.";normaRender()}catch{feedback.textContent="Não foi possível salvar no navegador."}
});
normaRender();
