/**
 * “收藏到 CareerCraft”书签。
 *
 * 用户在自己的浏览器里正常打开某个岗位详情页后手动点击：
 * 读取当前页面上的岗位文字 → 打开 CareerCraft 的 /clip 小窗口 → 用 postMessage 把文字交过去，
 * 由用户确认后保存。每次只处理用户正在看的这一页，不批量抓取、不绕过登录或验证。
 *
 * 用 window.open + postMessage 而不是直接 fetch 本地接口，是因为招聘网站的 CSP、跨域和
 * 本地网络访问限制都会拦截 fetch，而且书签脚本拿不到 CareerCraft 的登录 token。
 */
export function buildBookmarklet(appOrigin: string): string {
  const code = `(function(){
var A=${JSON.stringify(appOrigin)};
var sel=String(window.getSelection()||'').trim();
var text=(document.body.innerText||'').slice(0,30000);
var body=document.body.cloneNode(true);
var src=document.body.querySelectorAll('span'),dst=body.querySelectorAll('span'),hidden=[];
for(var i=0;i<src.length&&i<dst.length;i++){var st=getComputedStyle(src[i]);if(st.display==='none'||st.visibility==='hidden'||st.fontSize==='0px')hidden.push(dst[i]);}
hidden.forEach(function(e){e.remove()});
body.querySelectorAll('script,style,svg,img,iframe,noscript').forEach(function(e){e.remove()});
var html=body.innerHTML.slice(0,1500000);
var msg={source:'careercraft-clip',version:2,url:location.href,title:document.title,selection:sel.slice(0,20000),html:html,text:text};
var w=window.open(A+'/clip','careercraft_clip','width=760,height=820');
if(!w){alert('浏览器拦截了弹出窗口，请允许本网站弹窗后再点一次');return;}
var n=0,t=setInterval(function(){try{w.postMessage(msg,A)}catch(e){}if(++n>60)clearInterval(t)},500);
window.addEventListener('message',function(e){if(e.origin===A&&e.data==='careercraft-clip-ok')clearInterval(t)});
})();`
  return 'javascript:' + encodeURIComponent(code.replace(/\n/g, ''))
}

/** 只接受来自这些招聘网站的收藏消息（防止任意网站往你的账号里塞数据）。 */
export const CLIP_ALLOWED_HOSTS = [
  'zhipin.com', 'liepin.com', 'lagou.com', '51job.com', 'zhaopin.com', 'shixiseng.com', 'nowcoder.com',
]

export function isAllowedClipOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname
    return CLIP_ALLOWED_HOSTS.some((h) => host === h || host.endsWith('.' + h))
  } catch {
    return false
  }
}

/** 批量粘贴：用单独一行的 --- 分隔多个岗位；每段里出现的第一个链接作为原文链接。 */
export function splitJobs(raw: string): { text: string; url: string }[] {
  return raw
    .split(/\n\s*-{3,}\s*\n/)
    .map((block) => block.trim())
    .filter((block) => block.length >= 20)
    .map((block) => ({ text: block, url: (block.match(/https?:\/\/[^\s，。）)]+/) || [''])[0] }))
}
