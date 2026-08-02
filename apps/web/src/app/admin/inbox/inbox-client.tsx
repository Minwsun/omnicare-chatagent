"use client";

import { FormEvent, useEffect, useState } from "react";

type TicketSummary = { id:string; status:string; priority:string; category:string; summary:string; assignedTo:string|null; updatedAt:string; customer?:{name:string;email:string}; conversation:{title:string|null;lastMessageAt:string;_count:{messages:number}} };
type Message = { id:string; direction:"INBOUND"|"OUTBOUND"; content:string; createdAt:string; metadata?:{source?:string}; attachments?:{id:string;fileName:string}[] };
type TicketDetail = TicketSummary & { customer?:Record<string,unknown>; order?:Record<string,unknown>; events:{id:string;type:string;createdAt:string;payload?:unknown}[]; conversation:TicketSummary["conversation"] & { messages:Message[]; aiRuns:unknown[] } };
type Assist = { summary:string; missing_information:string[]; next_action:string; reply_options:string[]; warnings:string[] };

export default function InboxClient() {
  const [tickets,setTickets]=useState<TicketSummary[]>([]);
  const [selectedId,setSelectedId]=useState<string>();
  const [detail,setDetail]=useState<TicketDetail>();
  const [adminId,setAdminId]=useState("");
  const [reply,setReply]=useState("");
  const [assist,setAssist]=useState<Assist>();
  const [busy,setBusy]=useState(false);
  const [assignment,setAssignment]=useState("all");

  async function loadTickets() {
    const response=await fetch(`/api/admin/inbox?assignment=${assignment}`,{cache:"no-store"});
    if (!response.ok) return;
    const data=await response.json(); setTickets(data.tickets); setAdminId(data.adminId);
    if (!selectedId && data.tickets[0]) setSelectedId(data.tickets[0].id);
  }
  async function loadDetail(id=selectedId) {
    if (!id) return;
    const response=await fetch(`/api/admin/tickets/${id}`,{cache:"no-store"});
    if (response.ok) setDetail((await response.json()).ticket);
  }
  useEffect(()=>{ void loadTickets(); },[assignment]);
  useEffect(()=>{ if(selectedId) void loadDetail(selectedId); },[selectedId]);
  useEffect(()=>{ const timer=setInterval(()=>{void loadTickets();void loadDetail();},3000);return()=>clearInterval(timer); });

  async function action(path:string,body?:unknown) {
    setBusy(true);
    const response=await fetch(`/api/admin/tickets/${selectedId}/${path}`,{method:"POST",headers:{"content-type":"application/json"},body:body?JSON.stringify(body):undefined});
    setBusy(false);
    if (!response.ok) return;
    await Promise.all([loadTickets(),loadDetail()]);
  }
  async function send(event:FormEvent) {
    event.preventDefault(); if(!reply.trim()) return;
    const content=reply; setReply(""); await action("reply",{content});
  }
  async function loadAssist() {
    setBusy(true); const response=await fetch(`/api/admin/tickets/${selectedId}/ai-assist`,{method:"POST"}); setBusy(false);
    if(response.ok) setAssist(await response.json());
  }

  const mine=detail?.assignedTo===adminId;
  return <div className="inbox-layout">
    <aside className="ticket-queue"><div className="inbox-toolbar"><select value={assignment} onChange={(event)=>setAssignment(event.target.value)}><option value="all">Tất cả</option><option value="unassigned">Chưa nhận</option><option value="mine">Của tôi</option></select><button onClick={()=>loadTickets()}>Làm mới</button></div>{tickets.map(ticket=><button className={ticket.id===selectedId?"active":""} key={ticket.id} onClick={()=>setSelectedId(ticket.id)}><span className={`priority ${ticket.priority.toLowerCase()}`}>{ticket.priority}</span><b>{ticket.customer?.name||ticket.id}</b><p>{ticket.summary}</p><small>{ticket.id} · {ticket.category} · {ticket.conversation._count.messages} tin</small></button>)}{!tickets.length&&<p className="empty-state">Không có yêu cầu đang mở.</p>}</aside>
    <section className="ticket-workspace">{detail?<><header className="ticket-header"><div><small>{detail.id} · {detail.category}</small><h2>{detail.customer?.name as string||"Khách hàng"}</h2><p>{detail.summary}</p></div><div className="ticket-actions">{!detail.assignedTo&&<button disabled={busy} onClick={()=>action("claim")}>Nhận xử lý</button>}{mine&&<><button onClick={()=>action("status",{action:"WAIT_CUSTOMER"})}>Chờ khách</button><button onClick={()=>action("status",{action:"RESOLVE"})}>Đã xử lý</button><button onClick={()=>action("status",{action:"RELEASE_AI"})}>Trả lại AI</button></>}</div></header>
      <div className="operator-grid"><div className="operator-chat"><div className="operator-messages">{detail.conversation.messages.map(message=><article key={message.id} className={message.direction==="INBOUND"?"customer":"outbound"}><small>{message.direction==="INBOUND"?"Khách hàng":message.metadata?.source==="HUMAN_ADMIN"?"Nhân viên Omni":"Omni AI"}</small><p>{message.content}</p><time>{new Date(message.createdAt).toLocaleString("vi-VN")}</time>{message.attachments?.map(file=><a key={file.id} href={`/api/chat/attachments/${file.id}`} target="_blank">{file.fileName}</a>)}</article>)}</div><form onSubmit={send} className="operator-composer"><textarea value={reply} onChange={event=>setReply(event.target.value)} placeholder={mine?"Nhập phản hồi cho khách hàng":"Nhận xử lý trước khi trả lời"} disabled={!mine||busy}/><button disabled={!mine||busy||!reply.trim()}>Gửi</button></form></div>
      <aside className="operator-assist"><button onClick={loadAssist} disabled={busy}>Tạo gợi ý AI</button>{assist&&<><h3>Tóm tắt</h3><p>{assist.summary}</p><h3>Bước tiếp theo</h3><p>{assist.next_action}</p>{assist.missing_information.length>0&&<><h3>Cần bổ sung</h3><ul>{assist.missing_information.map(item=><li key={item}>{item}</li>)}</ul></>}{assist.warnings.length>0&&<><h3>Cảnh báo</h3><ul>{assist.warnings.map(item=><li key={item}>{item}</li>)}</ul></>}<h3>Phản hồi gợi ý</h3>{assist.reply_options.map(option=><button className="reply-option" key={option} onClick={()=>setReply(option)}>{option}</button>)}</>}<details><summary>Dữ liệu liên quan</summary><pre>{JSON.stringify({customer:detail.customer,order:detail.order},null,2)}</pre></details><details><summary>Timeline</summary>{detail.events.map(event=><p key={event.id}><b>{event.type}</b><br/><small>{new Date(event.createdAt).toLocaleString("vi-VN")}</small></p>)}</details></aside></div>
    </>:<p className="empty-state">Chọn một yêu cầu hỗ trợ.</p>}</section>
  </div>;
}
