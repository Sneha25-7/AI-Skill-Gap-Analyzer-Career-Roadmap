from flask import Flask,render_template,request,jsonify
import os,json,re,sqlite3
from datetime import datetime
from difflib import SequenceMatcher

BASE=os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE,"data","roles.json"),encoding="utf8") as f: DATA=json.load(f)
ROLES=DATA["roles"]; SKILLS=DATA["skills"]; DETAILS=DATA["details"]
DB=os.path.join(BASE,"instance","skillforge.db"); UP=os.path.join(BASE,"uploads")
app=Flask(__name__); app.secret_key="skillforge-ai"

ALIASES={"ml":"Machine Learning","dl":"Deep Learning","js":"JavaScript","ts":"TypeScript","nodejs":"Node.js","powerbi":"Power BI","sklearn":"Scikit-learn","genai":"Generative AI","llms":"LLM","gcp":"Google Cloud","postgres":"PostgreSQL"}

def init():
 os.makedirs(os.path.dirname(DB),exist_ok=True); os.makedirs(UP,exist_ok=True)
 c=sqlite3.connect(DB)
 c.execute("""CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY,name TEXT,role TEXT,score REAL,gaps INTEGER,source TEXT,created TEXT)""")
 c.execute("""CREATE TABLE IF NOT EXISTS progress(id INTEGER PRIMARY KEY,candidate TEXT,skill TEXT,status TEXT,updated TEXT,UNIQUE(candidate,skill))""")
 c.commit();c.close()
def norm(x): return re.sub(r"[^a-z0-9+#.]","",(x or "").lower())
def extract(text):
 raw=(text or "").lower(); n=norm(raw); out=set()
 for k,v in ALIASES.items():
  if k in n: out.add(v)
 for s in SKILLS:
  if s.lower() in raw: out.add(s)
 return sorted(out)
def similarity(a,b):
 a,b=norm(a),norm(b)
 if a==b:return 1
 if a in b or b in a:return .94
 return SequenceMatcher(None,a,b).ratio()
def score_role(have,role):
 matched=[];missing=[]
 for req in role["skills"]:
  ok=max([similarity(x,req) for x in have],default=0)>=.84
  (matched if ok else missing).append(req)
 return matched,missing
def career_recs(text):
 have=extract(text); out=[]
 for r in ROLES:
  m,g=score_role(have,r); out.append({"title":r["title"],"category":r["category"],"score":round(len(m)/len(r["skills"])*100,1),"gaps":len(g)})
 return sorted(out,key=lambda x:x["score"],reverse=True)

@app.route("/")
def home(): return render_template("index.html",roles=ROLES,skills=SKILLS)
@app.route("/analyze",methods=["POST"])
def analyze():
 d=request.get_json() or {}; role=next((r for r in ROLES if r["title"]==d.get("role")),None)
 if not role:return jsonify(success=False,error="Select a target career."),400
 have=extract(d.get("skills","")); m,g=score_role(have,role); sc=round(len(m)/len(role["skills"])*100,1)
 roadmap=[]
 for i,s in enumerate(g,1):
  q=DETAILS[s]; roadmap.append({"step":i,"skill":s,**q})
 result={"name":d.get("name") or "Candidate","role":role,"have":have,"matched":m,"missing":g,"score":sc,
 "status":"Excellent" if sc>=85 else "Strong" if sc>=70 else "Developing" if sc>=50 else "Beginner","roadmap":roadmap}
 c=sqlite3.connect(DB);c.execute("INSERT INTO analyses(name,role,score,gaps,source,created) VALUES(?,?,?,?,?,?)",(result["name"],role["title"],sc,len(g),"Manual",datetime.now().strftime("%Y-%m-%d %H:%M:%S")));c.commit();c.close()
 return jsonify(success=True,result=result)
@app.route("/recommend",methods=["POST"])
def recommend():
 return jsonify(success=True,recommendations=career_recs((request.get_json() or {}).get("skills","")))
@app.route("/resume",methods=["POST"])
def resume():
 f=request.files.get("resume")
 if not f or not f.filename.lower().endswith(".pdf"): return jsonify(success=False,error="Upload a PDF resume."),400
 p=os.path.join(UP,"resume.pdf");f.save(p)
 try:
  from pypdf import PdfReader
  text="\n".join(x.extract_text() or "" for x in PdfReader(p).pages)
 except ImportError:return jsonify(success=False,error="Install pypdf: pip install pypdf"),400
 return jsonify(success=True,skills=extract(text),preview=text[:1500])
@app.route("/job-match",methods=["POST"])
def jobmatch():
 d=request.get_json() or {}; candidate=extract(d.get("skills","")); job=extract(d.get("job",""))
 matched=[s for s in job if max([similarity(x,s) for x in candidate],default=0)>=.84]
 missing=[s for s in job if s not in matched]
 return jsonify(success=True,score=round(len(matched)/len(job)*100,1) if job else 0,matched=matched,missing=missing,job_skills=job)
@app.route("/progress",methods=["POST"])
def set_progress():
 d=request.get_json() or {}; c=sqlite3.connect(DB)
 c.execute("""INSERT INTO progress(candidate,skill,status,updated) VALUES(?,?,?,?)
 ON CONFLICT(candidate,skill) DO UPDATE SET status=excluded.status,updated=excluded.updated""",(d.get("candidate","Candidate"),d["skill"],d["status"],datetime.now().strftime("%Y-%m-%d %H:%M:%S")));c.commit();c.close()
 return jsonify(success=True)
@app.route("/dashboard")
def dashboard():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 rows=c.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT 50").fetchall();c.close()
 avg=round(sum(r["score"] for r in rows)/len(rows),1) if rows else 0
 return render_template("dashboard.html",rows=rows,avg=avg,roles=len(ROLES),skills=len(SKILLS))
if __name__=="__main__": init();app.run(debug=True)
