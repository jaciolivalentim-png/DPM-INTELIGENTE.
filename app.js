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
  lastDispatchAnalysis=d;
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
  const normBox=document.getElementById("normativeMatches");normBox.replaceChildren();
  document.getElementById("normativeNotice").textContent=d.normative_notice||"Nenhum texto normativo cadastrado para pesquisa; consultar fontes oficiais.";
  if(!(d.normative_matches||[]).length){const p=document.createElement("p");p.textContent="Nenhum trecho relacionado localizado nos PDFs cadastrados.";normBox.append(p)}
  (d.normative_matches||[]).forEach(n=>{const item=document.createElement("article");item.className="norma-item";
    const title=document.createElement("h4");title.textContent=n.title;
    const excerpt=document.createElement("p");excerpt.textContent=(n.page?`Página ${n.page} — `:"")+n.excerpt;
    const notice=document.createElement("p");notice.className="muted";notice.textContent=n.status;
    item.append(title,excerpt,notice);
    if(n.source_url&&normaValidUrl(n.source_url)){const a=document.createElement("a");a.href=n.source_url;a.target="_blank";a.rel="noopener noreferrer";a.textContent="Conferir fonte oficial";item.append(a)}
    normBox.append(item)});
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
let historyFolder = 'all';
let historyUsers = [];
let protocolFolder = 'all';
let protocolStatus = 'all';
async function historyAction(url,method,body){
 const res=await fetch(url,{method,credentials:'same-origin',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
 const data=await res.json();if(!res.ok)throw Error(data.error||'Não foi possível atualizar o registro.');return data;
}
async function loadHistoryUsers(){
 try{
  const r=await fetch('/api/history/users',{credentials:'same-origin'});
  if(!r.ok)throw Error('Não foi possível carregar usuários');
  historyUsers=(await r.json()).users;
  const sel=document.getElementById('historyFolder');const prior=sel.value;
  sel.replaceChildren();
  [['all','Todas as pastas'],['mine','Minhas análises'],['unassigned','Não atribuídos'],...historyUsers.map(u=>['user:'+u.id,'Pasta: '+u.username])].forEach(([v,t])=>{const o=new Option(t,v);sel.add(o)});
  sel.value=prior||'all';if(sel.selectedIndex<0)sel.value='all';historyFolder=sel.value;
  const psel=document.getElementById('protocolFolder');if(psel){const old=psel.value;psel.replaceChildren();[['all','Todas as pastas'],['mine','Minhas análises'],['unassigned','Não atribuídos'],...historyUsers.map(u=>['user:'+u.id,'Pasta: '+u.username])].forEach(([v,t])=>psel.add(new Option(t,v)));psel.value=old;if(psel.selectedIndex<0)psel.value='all';protocolFolder=psel.value;}
 }catch(e){console.warn(e.message)}
}
async function loadHistory(){
 const area=document.getElementById('historyList');
 try {
  const res=await fetch('/api/history?view='+encodeURIComponent(historyView)+'&folder='+encodeURIComponent(historyFolder),{credentials:'same-origin'});
  const data=await res.json();if(!res.ok)throw Error(data.error||'Falha ao carregar histórico');
  area.replaceChildren();
  for(const i of data.items){
   const el=document.createElement('div');el.className='history-item';
   const strong=document.createElement('strong');strong.textContent='Registro #'+i.id+' — '+(i.protocol_label||'Sem identificador');
   const desc=document.createElement('p');desc.textContent=i.username+' | '+new Date(i.created_at).toLocaleString('pt-BR')+' | '+i.document_count+' documento(s) | '+i.page_count+' página(s)'+(i.archived?' | Arquivado':'')+' | Responsável: '+(i.assignee||'Não atribuído');
   const actions=document.createElement('div');actions.className='history-actions';
   const archive=document.createElement('button');archive.type='button';archive.textContent=i.archived?'Restaurar':'Arquivar';
   archive.addEventListener('click',async()=>{try{archive.disabled=true;await historyAction('/api/history/'+i.id+'/archive','PATCH',{archived:!i.archived});await loadHistory()}catch(e){alert(e.message);archive.disabled=false}});
   const reopen=document.createElement('button');reopen.type='button';reopen.textContent='Rever análise';
   reopen.disabled=!i.has_report;
   reopen.title=i.has_report?'Abrir relatório salvo':'Este registro não tem relatório salvo';
   reopen.addEventListener('click',async()=>{try{const r=await fetch('/api/history/'+i.id+'/report',{credentials:'same-origin'});const d=await r.json();if(!r.ok)throw Error(d.error||'Relatório indisponível');navigate('analise');showResult(d)}catch(e){alert(e.message)}});
   actions.append(reopen,archive);
   if(window.currentRole==='admin'){
    const select=document.createElement('select');select.setAttribute('aria-label','Responsável pelo protocolo');
    select.add(new Option('Não atribuído',''));
    historyUsers.forEach(u=>select.add(new Option(u.username+' ('+u.role+')',String(u.id))));
    select.value=i.assigned_to==null?'':String(i.assigned_to);
    const move=document.createElement('button');move.type='button';move.textContent='Mover para pasta';
    move.addEventListener('click',async()=>{try{move.disabled=true;await historyAction('/api/history/'+i.id+'/assign','PATCH',{user_id:select.value?Number(select.value):null});await loadHistory()}catch(e){alert(e.message);move.disabled=false}});
    actions.append(select,move);
   }
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
document.getElementById('refreshHistory').addEventListener('click',async()=>{await loadHistoryUsers();await loadHistory()});
document.getElementById('historyFolder').addEventListener('change',e=>{historyFolder=e.target.value;loadHistory()});
document.querySelector('[data-page="historico"]').addEventListener('click',async()=>{await loadHistoryUsers();await loadHistory()});
let selectedProtocolFolder=null;
const protocolFolderItems=()=>[
 {id:'mine',title:'Meus protocolos',description:'Sob minha responsabilidade',icon:'📁'},
 {id:'unassigned',title:'Não atribuídos',description:'Aguardando distribuição',icon:'📁'},
 {id:'status:pending',title:'Pendentes',description:'Aguardando providências',icon:'📁'},
 {id:'status:in_progress',title:'Em análise',description:'Em andamento',icon:'📁'},
 {id:'status:completed',title:'Concluídos',description:'Finalizados',icon:'📁'},
 ...historyUsers.map(u=>({id:'user:'+u.id,title:'Pasta: '+u.username,description:u.role==='admin'?'Administrador':'Analista',icon:'📁'}))
];
function renderProtocolFolders(){
 const area=document.getElementById('protocolFolders'),inside=document.getElementById('protocolInside'),crumb=document.getElementById('protocolBreadcrumb');
 area.replaceChildren();crumb.replaceChildren();
 const home=document.createElement('button');home.type='button';home.className='protocol-back';home.textContent='⌂ Todas as pastas';home.addEventListener('click',()=>{selectedProtocolFolder=null;renderProtocolFolders()});crumb.append(home);
 if(!selectedProtocolFolder){inside.hidden=true;area.hidden=false;
  for(const folder of protocolFolderItems()){
   const btn=document.createElement('button');btn.type='button';btn.className='protocol-folder';
   const ico=document.createElement('span');ico.className='protocol-folder-icon';ico.textContent=folder.icon;
   const content=document.createElement('span');const name=document.createElement('strong');name.textContent=folder.title;const desc=document.createElement('small');desc.textContent=folder.description;content.append(name,desc);btn.append(ico,content);
   btn.addEventListener('click',()=>{selectedProtocolFolder=folder.id;protocolStatus='all';document.getElementById('protocolStatus').value='all';renderProtocolFolders();loadProtocols()});area.append(btn);
  }
 }else{area.hidden=true;inside.hidden=false;const label=document.createElement('strong');label.textContent=' / '+(protocolFolderItems().find(f=>f.id===selectedProtocolFolder)?.title||'Pasta');crumb.append(label)}
}
async function loadProtocols(){
 if(!selectedProtocolFolder)return;
 const area=document.getElementById('protocolList');area.textContent='Carregando...';
 let folder=selectedProtocolFolder, status=protocolStatus;
 if(folder.startsWith('status:')){status=folder.slice(7);folder='all'}
 try{
  const r=await fetch('/api/history?view=active&folder='+encodeURIComponent(folder)+'&review_status='+encodeURIComponent(status),{credentials:'same-origin'});
  const data=await r.json();if(!r.ok)throw Error(data.error||'Erro ao carregar protocolos');area.replaceChildren();
  const note=document.getElementById('protocolStorageNotice');
  note.textContent='O botão Rever análise só funciona quando o relatório foi salvo no servidor. O armazenamento permanece desativado por padrão; não habilite para documentos médicos reais sem autorização institucional.';
  for(const i of data.items){
   const el=document.createElement('div');el.className='history-item';
   const title=document.createElement('strong');title.textContent='Registro #'+i.id+' — '+(i.protocol_label||'Sem identificador');
   const info=document.createElement('p');info.textContent='Criado por '+i.username+' | '+new Date(i.created_at).toLocaleString('pt-BR')+' | Responsável: '+(i.assignee||'Não atribuído')+' | '+i.page_count+' página(s)';
   const actions=document.createElement('div');actions.className='history-actions';
   const reopen=document.createElement('button');reopen.type='button';reopen.textContent='Rever análise';reopen.disabled=!i.has_report;reopen.title=i.has_report?'Abrir relatório salvo':'Este relatório não foi armazenado';
   reopen.addEventListener('click',async()=>{try{const r=await fetch('/api/history/'+i.id+'/report',{credentials:'same-origin'});const d=await r.json();if(!r.ok)throw Error(d.error||'Relatório indisponível');navigate('analise');showResult(d)}catch(e){alert(e.message)}});actions.append(reopen);
   if(!i.has_report){const label=document.createElement('span');label.className='muted';label.textContent='Relatório não salvo';actions.append(label)}
   const statusSelect=document.createElement('select');statusSelect.setAttribute('aria-label','Situação do protocolo');[['pending','Pendente'],['in_progress','Em análise'],['completed','Concluído']].forEach(([v,t])=>statusSelect.add(new Option(t,v)));statusSelect.value=i.review_status||'pending';
   statusSelect.addEventListener('change',async()=>{try{statusSelect.disabled=true;await historyAction('/api/history/'+i.id+'/status','PATCH',{status:statusSelect.value});await loadProtocols()}catch(e){alert(e.message);statusSelect.value=i.review_status||'pending';statusSelect.disabled=false}});actions.append(statusSelect);
   if(window.currentRole==='admin'){
    const select=document.createElement('select');select.setAttribute('aria-label','Pasta de destino');select.add(new Option('Não atribuído',''));historyUsers.forEach(u=>select.add(new Option(u.username+' ('+u.role+')',String(u.id))));select.value=i.assigned_to==null?'':String(i.assigned_to);
    const move=document.createElement('button');move.type='button';move.textContent='Mover para pasta';move.addEventListener('click',async()=>{try{move.disabled=true;await historyAction('/api/history/'+i.id+'/assign','PATCH',{user_id:select.value?Number(select.value):null});await loadProtocols()}catch(e){alert(e.message);move.disabled=false}});actions.append(select,move);
   }
   el.append(title,info,actions);area.append(el);
  }
  if(!data.items.length)area.textContent='Nenhum protocolo nesta pasta ou situação.';
 }catch(e){area.textContent='Erro: '+e.message}
}
document.getElementById('protocolStatus').addEventListener('change',e=>{protocolStatus=e.target.value;loadProtocols()});
document.getElementById('refreshProtocols').addEventListener('click',async()=>{await loadHistoryUsers();renderProtocolFolders();await loadProtocols()});
document.querySelector('[data-page="protocolos"]').addEventListener('click',async()=>{await loadHistoryUsers();selectedProtocolFolder=null;renderProtocolFolders()});

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
const NORMA_OFFICIAL = [
 {title:"Regulamentos — Saúde do Servidor (SAS/SEAP)",category:"Portal oficial",subject:"Índice oficial com legislação do SAS e Manual de Perícia Médica.",url:"https://www.administracao.pr.gov.br/SAS/Pagina/Regulamentos",official:true},
 {title:"Manual de Perícia Médica — Resolução SEAP nº 6.315/2024",category:"Manual e orientações",subject:"Manual de procedimentos médico-periciais, licenças, capacidade laboral, recursos e reconsideração. PDF publicado pela SEAP; verificar alterações posteriores.",url:"https://www.administracao.pr.gov.br/sites/default/arquivos_restritos/files/documento/2024-09/RESOLU%C3%87%C3%83O%20E%20MANUAL%2024%20%282%29.pdf",official:true},
 {title:"Resolução SEAP nº 6.315/2024",category:"Legislação",subject:"Aprovação do Manual de Perícia Médica; texto da resolução publicado pela SEAP.",url:"https://www.administracao.pr.gov.br/sites/default/arquivos_restritos/files/documento/2024-08/resolucao_seap_6315_2024_-_novo_manual_pericia_medica.pdf",official:true},
 {title:"Comunicado DRH nº 010/2024",category:"Manual e orientações",subject:"Comunicado institucional de divulgação do Manual de Perícia Médica aprovado pela Resolução SEAP nº 6.315/2024.",url:"https://www.administracao.pr.gov.br/sites/default/arquivos_restritos/files/documento/2024-08/comunicado010.2024novomanualpericiamedica.pdf",official:true},
 {title:"Decreto nº 13.043/2026 — legislação do SAS",category:"Legislação",subject:"Referência ao decreto indicado no portal oficial de Regulamentos da SAS; consultar texto e vigência na fonte.",url:"https://www.administracao.pr.gov.br/SAS/Pagina/Regulamentos",official:true},
 {title:"Perícias Médicas — orientações da SEAP",category:"Manual e orientações",subject:"Procedimentos, formulários, atestados, agendamentos e orientações públicas da DPM.",url:"https://www.administracao.pr.gov.br/SAS/Pagina/Pericias-Medicas",official:true},
 {title:"DPM — informações institucionais",category:"Portal oficial",subject:"Informações e perguntas frequentes sobre a Divisão de Perícia Médica.",url:"https://www.administracao.pr.gov.br/SAS/Pagina/Divisao-de-Pericia-Medica-DPM",official:true}
];
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

// Biblioteca normativa compartilhada: somente administradores podem cadastrar PDFs.
async function loadNormativeDocuments(){
 const box=document.getElementById('normativeStored');if(!box)return;
 try{const response=await fetch('/api/normative/documents',{credentials:'same-origin'});if(!response.ok)throw Error('Falha na consulta');
 const items=await response.json();box.replaceChildren();
 if(!items.length){box.textContent='Nenhum PDF normativo cadastrado no servidor.';return}
 items.forEach(n=>{const p=document.createElement('p');p.textContent=`${n.title} — ${n.active?'Disponível':'Desativado'} — ${n.characters} caracteres`;
 if(n.active){const b=document.createElement('button');b.type='button';b.textContent='Desativar (admin)';b.addEventListener('click',async()=>{if(!confirm('Desativar esta norma para pesquisas futuras?'))return;const r=await fetch(`/api/normative/documents/${n.id}`,{method:'DELETE',credentials:'same-origin'});if(!r.ok){alert('Somente administradores podem desativar.');return}loadNormativeDocuments()});p.append(' ',b)}box.append(p)})
 }catch{box.textContent='Não foi possível carregar os PDFs normativos.'}
}
document.querySelector('[data-page="normas"]')?.addEventListener('click',loadNormativeDocuments);
document.getElementById('normativeUpload')?.addEventListener('submit',async e=>{
 e.preventDefault();const status=document.getElementById('normativeUploadStatus');status.textContent='Extraindo texto do PDF...';
 try{const r=await fetch('/api/normative/documents',{method:'POST',body:new FormData(e.target),credentials:'same-origin'});const data=await r.json();
 if(!r.ok)throw Error(data.error||'Falha no cadastro');status.textContent=`${data.message} (${data.characters} caracteres)`;e.target.reset();loadNormativeDocuments()
 }catch(error){status.textContent=error.message||'Falha ao cadastrar'}
});


// Modelos de despacho 5.4: textos revisáveis e cadastro compartilhado.
let dispatchModels=[],dispatchSelectedModel=null,lastDispatchAnalysis=null;
const dispatchEl=id=>document.getElementById(id);
async function dispatchRequest(url,options={}){
 const headers={...(options.headers||{})};
 if(options.body){headers['Content-Type']='application/json';headers['X-CSRF-Token']=csrfToken;}
 else if(options.method==='DELETE')headers['X-CSRF-Token']=csrfToken;
 const response=await fetch(url,{credentials:'same-origin',...options,headers});
 const data=await response.json();if(!response.ok)throw Error(data.error||'Não foi possível concluir a operação.');return data;
}
async function loadDispatchModels(){
 try{dispatchModels=await dispatchRequest('/api/dispatch-templates');renderDispatchModels()}
 catch(e){dispatchEl('dispatchList').textContent=e.message}
 dispatchEl('dispatchAdminPanel').hidden=window.currentRole!=='admin';
}
function renderDispatchModels(){
 const box=dispatchEl('dispatchList');box.replaceChildren();
 const term=dispatchEl('dispatchSearch').value.trim().toLocaleLowerCase('pt-BR'),fmt=dispatchEl('dispatchFormat').value,audience=dispatchEl('dispatchAudience').value;
 const filtered=dispatchModels.filter(x=>(!fmt||x.format===fmt)&&(!audience||x.category===audience)&&[x.title,x.category,x.body].join(' ').toLocaleLowerCase('pt-BR').includes(term));
 if(!filtered.length){box.textContent='Nenhum modelo encontrado.';return}
 for(const m of filtered){
  const item=document.createElement('article');item.className='dispatch-card';
  const title=document.createElement('strong');title.textContent=m.title;
  const meta=document.createElement('p');meta.className='muted';meta.textContent=`${m.category} • ${m.format==='completo'?'Completo':'Simplificado'} • ${m.is_builtin?'Modelo inicial':'Modelo cadastrado'}`;
  const actions=document.createElement('div');actions.className='dispatch-actions';
  const view=document.createElement('button');view.type='button';view.textContent='Visualizar';view.addEventListener('click',()=>{dispatchSelectedModel=m;dispatchEl('dispatchSelected').textContent=`${m.title} — ${m.format}`;dispatchEl('dispatchEditor').value=m.body;dispatchEl('dispatchFeedback').textContent='Revise os campos antes de utilizar.'});actions.append(view);
  if(window.currentRole==='admin'&&!m.is_builtin){
   const edit=document.createElement('button');edit.type='button';edit.textContent='Editar';edit.addEventListener('click',()=>{dispatchEl('dispatchEditId').value=m.id;dispatchEl('dispatchTitle').value=m.title;dispatchEl('dispatchCategory').value=m.category;dispatchEl('dispatchNewFormat').value=m.format;dispatchEl('dispatchBody').value=m.body;dispatchEl('dispatchSave').textContent='Salvar alterações';dispatchEl('dispatchAdminPanel').scrollIntoView({behavior:'smooth',block:'start'})});actions.append(edit);
   const remove=document.createElement('button');remove.type='button';remove.textContent='Desativar';remove.addEventListener('click',async()=>{if(!confirm('Desativar este modelo para toda a equipe?'))return;try{await dispatchRequest('/api/dispatch-templates/'+m.id,{method:'DELETE'});if(dispatchSelectedModel?.id===m.id){dispatchSelectedModel=null;dispatchEl('dispatchSelected').textContent='Nenhum modelo selecionado.';dispatchEl('dispatchEditor').value=''}await loadDispatchModels()}catch(e){dispatchEl('dispatchAdminFeedback').textContent=e.message}});actions.append(remove)
  }
  item.append(title,meta,actions);box.append(item)
 }
}
function resetDispatchForm(){dispatchEl('dispatchForm').reset();dispatchEl('dispatchEditId').value='';dispatchEl('dispatchSave').textContent='Salvar modelo'}
dispatchEl('dispatchSearch').addEventListener('input',renderDispatchModels);
dispatchEl('dispatchFormat').addEventListener('change',renderDispatchModels);
dispatchEl('dispatchAudience').addEventListener('change',renderDispatchModels);
document.querySelector('[data-page="modelos"]').addEventListener('click',loadDispatchModels);
dispatchEl('dispatchCancel').addEventListener('click',resetDispatchForm);
dispatchEl('dispatchForm').addEventListener('submit',async e=>{
 e.preventDefault();const status=dispatchEl('dispatchAdminFeedback');status.textContent='Salvando...';
 const id=dispatchEl('dispatchEditId').value;
 const data={title:dispatchEl('dispatchTitle').value.trim(),category:dispatchEl('dispatchCategory').value.trim(),format:dispatchEl('dispatchNewFormat').value,body:dispatchEl('dispatchBody').value.trim()};
 try{await dispatchRequest(id?'/api/dispatch-templates/'+id:'/api/dispatch-templates',{method:id?'PATCH':'POST',body:JSON.stringify(data)});resetDispatchForm();status.textContent='Modelo salvo para a equipe.';await loadDispatchModels()}catch(error){status.textContent=error.message}
});
dispatchEl('dispatchCopy').addEventListener('click',async()=>{
 const content=dispatchEl('dispatchEditor').value;if(!content.trim()){dispatchEl('dispatchFeedback').textContent='Selecione um modelo primeiro.';return}
 try{await navigator.clipboard.writeText(content);dispatchEl('dispatchFeedback').textContent='Texto copiado. Confira os dados antes de utilizar.'}catch{dispatchEl('dispatchFeedback').textContent='Não foi possível copiar automaticamente. Selecione o texto e copie manualmente.'}
});
dispatchEl('dispatchUseAnalysis').addEventListener('click',()=>{
 const text=dispatchEl('dispatchEditor').value;if(!text.trim()){dispatchEl('dispatchFeedback').textContent='Selecione um modelo primeiro.';return}
 if(!lastDispatchAnalysis){dispatchEl('dispatchFeedback').textContent='Faça uma análise nesta sessão antes de preencher os campos.';return}
 const d=lastDispatchAnalysis;
 const protocol=String(d.protocol||'').trim(),subject=String(d.subject||'').trim();
 dispatchEl('dispatchEditor').value=text.replaceAll('[PROTOCOLO]',protocol||'[PROTOCOLO]').replaceAll('[ASSUNTO]',subject||'[ASSUNTO]');
 dispatchEl('dispatchFeedback').textContent='Protocolo e assunto preenchidos quando disponíveis. Confira os demais campos manualmente.';
});
