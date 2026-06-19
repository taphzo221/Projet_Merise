"""
================================================================
SGRDMS — Le Tropical · Centre de Santé
Université Iba Der Thiam de Thiès · L2 Génie Logiciel · 2026
================================================================
  python app.py          →  http://127.0.0.1:5000
  Comptes par défaut:
    admin      / admin123  (Administrateur)
    accueil    / accueil123 (Réceptionniste)
    docteur    / medecin123 (Médecin)
    pharmacien / pharma123  (Pharmacien)
    patient1   / patient123 (Patient)
================================================================
"""

import sqlite3, os, re, secrets, string
from datetime import datetime, date, timedelta
from functools import wraps
from flask import (Flask, render_template_string, request, redirect,
                   url_for, session, flash, g, get_flashed_messages)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'sgrdms_le_tropical_2026_uidt_v2'
DATABASE = 'sgrdms.db'

# ================================================================
# DATABASE
# ================================================================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_db(e):
    db = getattr(g, '_database', None)
    if db: db.close()

def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv  = cur.fetchall(); cur.close()
    return (rv[0] if rv else None) if one else rv

def ex(sql, args=()):
    db = get_db(); cur = db.execute(sql, args); db.commit(); return cur.lastrowid

def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS utilisateurs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL, prenom TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL, mot_de_passe TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'accueil',
            medecin_id INTEGER, patient_id INTEGER,
            actif INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL, description TEXT
        );
        CREATE TABLE IF NOT EXISTS medecins(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL, prenom TEXT NOT NULL,
            specialite TEXT, telephone TEXT, email TEXT,
            service_id INTEGER REFERENCES services(id),
            teleconsultation_active INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS patients(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL, prenom TEXT NOT NULL,
            date_naissance DATE, sexe TEXT,
            telephone TEXT, email TEXT, adresse TEXT,
            num_dossier TEXT UNIQUE NOT NULL,
            groupe_sanguin TEXT, allergie TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS assurances(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL, type TEXT,
            plafond_annuel REAL DEFAULT 0, description TEXT
        );
        CREATE TABLE IF NOT EXISTS patient_assurance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER REFERENCES patients(id),
            assurance_id INTEGER REFERENCES assurances(id),
            numero_contrat TEXT,
            taux_prise_en_charge REAL DEFAULT 0,
            date_debut DATE, date_fin DATE
        );
        CREATE TABLE IF NOT EXISTS rendez_vous(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            medecin_id INTEGER NOT NULL REFERENCES medecins(id),
            date DATE NOT NULL, heure TEXT NOT NULL,
            statut TEXT DEFAULT 'planifie', motif TEXT,
            type TEXT DEFAULT 'presentiel',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS liste_attente(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            medecin_id INTEGER NOT NULL REFERENCES medecins(id),
            priorite INTEGER DEFAULT 1,
            date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS consultations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rdv_id INTEGER NOT NULL REFERENCES rendez_vous(id),
            diagnostic TEXT, notes TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ordonnances(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL REFERENCES consultations(id),
            date DATE DEFAULT CURRENT_DATE
        );
        CREATE TABLE IF NOT EXISTS medicaments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL, description TEXT,
            stock INTEGER DEFAULT 0, stock_minimum INTEGER DEFAULT 10,
            prix_unitaire REAL DEFAULT 0, date_expiration DATE, lot TEXT
        );
        CREATE TABLE IF NOT EXISTS lignes_ordonnance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordonnance_id INTEGER NOT NULL REFERENCES ordonnances(id),
            medicament_id INTEGER NOT NULL REFERENCES medicaments(id),
            dosage TEXT, frequence TEXT, duree TEXT, quantite INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS factures(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL REFERENCES consultations(id),
            montant_total REAL DEFAULT 0, montant_assurance REAL DEFAULT 0,
            montant_patient REAL DEFAULT 0,
            statut TEXT DEFAULT 'impayee', date DATE DEFAULT CURRENT_DATE
        );
        CREATE TABLE IF NOT EXISTS teleconsultations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rdv_id INTEGER NOT NULL REFERENCES rendez_vous(id),
            lien_session TEXT, statut TEXT DEFAULT 'planifiee',
            duree_minutes INTEGER, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER REFERENCES patients(id),
            titre TEXT NOT NULL, message TEXT NOT NULL,
            lu INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    if not db.execute("SELECT id FROM utilisateurs WHERE login='admin'").fetchone():
        users = [
            ('Administrateur','Système','admin',   generate_password_hash('admin123'),   'admin',       None, None),
            ('Sow',           'Fatou',  'accueil', generate_password_hash('accueil123'), 'accueil',     None, None),
            ('Ba',            'Ibrahima','docteur',generate_password_hash('medecin123'), 'medecin',     1,    None),
            ('Ndiaye',        'Mariama','pharmacien',generate_password_hash('pharma123'),'pharmacien',  None, None),
            ('Diallo',        'Moussa', 'patient1',generate_password_hash('patient123'), 'patient',     None, 1),
        ]
        db.executemany(
            "INSERT INTO utilisateurs(nom,prenom,login,mot_de_passe,role,medecin_id,patient_id) VALUES(?,?,?,?,?,?,?)",
            users)

        db.executemany("INSERT INTO services(nom,description) VALUES(?,?)",[
            ('Généraliste','Médecine générale'),
            ('Pédiatrie','Soins des enfants'),
            ('Gynécologie','Santé de la femme'),
            ('Chirurgie','Interventions chirurgicales'),
            ('Urgences','Prise en charge des urgences'),
            ('Cardiologie','Maladies cardiovasculaires'),
        ])
        db.executemany("INSERT INTO medecins(nom,prenom,specialite,service_id,telephone,teleconsultation_active) VALUES(?,?,?,?,?,?)",[
            ('Ba','Ibrahima','Médecine Générale',1,'+221 77 100 00 01',1),
            ('Sarr','Aminata','Pédiatrie',2,'+221 77 100 00 02',0),
            ('Fall','Ousmane','Chirurgie',4,'+221 77 100 00 03',0),
            ('Diop','Rokhaya','Gynécologie',3,'+221 77 100 00 04',1),
        ])
        db.executemany("INSERT INTO patients(nom,prenom,date_naissance,sexe,telephone,num_dossier,groupe_sanguin) VALUES(?,?,?,?,?,?,?)",[
            ('Diallo','Moussa','1990-05-14','M','+221 77 200 00 01','PAT-2026-0001','O+'),
            ('Mbaye','Adja','1985-11-20','F','+221 77 200 00 02','PAT-2026-0002','A+'),
            ('Ndiaye','Cheikh','2001-03-08','M','+221 77 200 00 03','PAT-2026-0003','B-'),
        ])
        exp1an = (date.today() + timedelta(days=365)).isoformat()
        db.executemany("INSERT INTO medicaments(nom,description,stock,stock_minimum,prix_unitaire,lot,date_expiration) VALUES(?,?,?,?,?,?,?)",[
            ('Paracétamol 500mg','Antalgique antipyrétique. Indiqué contre la douleur et la fièvre.',200,50,500,'LOT-001',exp1an),
            ('Amoxicilline 500mg','Antibiotique de la famille des pénicillines. Large spectre.',100,30,1500,'LOT-002',exp1an),
            ('Ibuprofène 400mg','Anti-inflammatoire non stéroïdien. Douleurs et inflammations.',150,40,800,'LOT-003',exp1an),
            ('Metformine 500mg','Antidiabétique oral de première intention (diabète type 2).',80,20,1200,'LOT-004',exp1an),
            ('Amlodipine 5mg','Antihypertenseur, inhibiteur calcique. HTA et angor.',60,15,2000,'LOT-005',exp1an),
            ('Oméprazole 20mg','Inhibiteur de la pompe à protons. Ulcères et RGO.',8,10,700,'LOT-006',exp1an),
        ])
        db.executemany("INSERT INTO assurances(nom,type,plafond_annuel) VALUES(?,?,?)",[
            ('IPRES','Publique',500000),('CSSF','Publique',300000),
            ('Allianz Sénégal','Privée',1000000),('Sanlam','Privée',750000),
        ])
    db.commit(); db.close()

# ================================================================
# HELPERS
# ================================================================
def login_required(f):
    @wraps(f)
    def deco(*a,**kw):
        if 'user_id' not in session: return redirect('/login')
        return f(*a,**kw)
    return deco

def roles_allowed(*roles):
    def dec(f):
        @wraps(f)
        def deco(*a,**kw):
            if session.get('user_role') not in roles:
                flash('Accès non autorisé pour votre rôle.','error')
                return redirect('/')
            return f(*a,**kw)
        return deco
    return dec

def gen_num_dossier():
    yr   = date.today().year
    last = q("SELECT num_dossier FROM patients ORDER BY id DESC LIMIT 1",one=True)
    try:   n = int(last['num_dossier'].split('-')[-1])+1 if last else 1
    except: n = 1
    return f"PAT-{yr}-{n:04d}"

def gen_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def gen_login(prenom, nom):
    base = f"{prenom.lower().replace(' ','')}.{nom.lower().replace(' ','')}"
    base = re.sub(r'[^a-z0-9.]', '', base)
    existing = q("SELECT login FROM utilisateurs WHERE login LIKE ?", [f'{base}%'])
    if not existing: return base
    for i in range(2, 999):
        candidate = f"{base}{i}"
        if not any(r['login'] == candidate for r in existing): return candidate
    return base + str(secrets.randbelow(9999))

def badge(statut):
    m = {'planifie':('Planifié','planifie'),'confirme':('Confirmé','confirme'),
         'annule':('Annulé','annule'),'effectue':('Effectué','effectue'),
         'teleconsultation':('Téléconsult.','tele'),
         'impayee':('Impayée','impayee'),'payee':('Payée','payee'),
         'partielle':('Partielle','partielle'),
         'planifiee':('Planifiée','planifie'),'en_cours':('En cours','confirme'),
         'terminee':('Terminée','effectue'),'annulee':('Annulée','annule')}
    label,cls = m.get(statut,(statut,'effectue'))
    return f'<span class="lt-badge lt-badge-{cls}">{label}</span>'

def fcfa(n):
    try: return f"{int(float(n or 0)):,} F".replace(',',' ')
    except: return "0 F"

def add_notification(patient_id, titre, message):
    try: ex("INSERT INTO notifications(patient_id,titre,message) VALUES(?,?,?)",[patient_id,titre,message])
    except: pass

ROLE_LABELS = {'admin':'Administrateur','accueil':'Accueil','medecin':'Médecin',
               'pharmacien':'Pharmacien','patient':'Patient'}
ROLE_COLORS = {'admin':'#0B5735','accueil':'#0E6D43','medecin':'#138555',
               'pharmacien':'#1EA068','patient':'#0D6644'}
ROLE_ICONS  = {'admin':'bi-shield-fill','accueil':'bi-headset',
               'medecin':'bi-heart-pulse-fill','pharmacien':'bi-capsule',
               'patient':'bi-person-heart'}

def get_menu(role):
    ALL = [
        ('dashboard',       '/',                 'bi-grid-fill',          'Tableau de bord'),
        ('patients',        '/patients',          'bi-people-fill',        'Patients'),
        ('medecins',        '/medecins',          'bi-person-badge-fill',  'Médecins &amp; Services'),
        ('rendez_vous',     '/rendez-vous',       'bi-calendar-check-fill','Rendez-vous'),
        ('mes_rdv',         '/mes-rdv',           'bi-calendar-heart-fill','Mes Rendez-vous'),
        ('consultations',   '/consultations',     'bi-clipboard2-pulse-fill','Consultations'),
        ('pharmacie',       '/pharmacie',         'bi-bag-heart-fill',     'Pharmacie &amp; Stocks'),
        ('facturation',     '/facturation',       'bi-receipt-cutoff',     'Facturation'),
        ('assurances',      '/assurances',        'bi-shield-fill-check',  'Assurances'),
        ('teleconsultation','/teleconsultation',  'bi-camera-video-fill',  'Téléconsultation'),
        ('mon_dossier',     '/mon-dossier',       'bi-folder2-open',       'Mon Dossier'),
        ('mes_notifications','/mes-notifications','bi-bell-fill',          'Mes Messages'),
        ('utilisateurs',    '/utilisateurs',      'bi-person-lines-fill',  'Gestion Comptes'),
    ]
    perms = {
        'admin':       {'dashboard','patients','medecins','rendez_vous','consultations','pharmacie','facturation','assurances','teleconsultation','utilisateurs'},
        'accueil':     {'dashboard','patients','rendez_vous','consultations','facturation','assurances'},
        # ── CORRECTION : 'rendez_vous' retiré du menu médecin ──
        'medecin':     {'dashboard','mes_rdv','patients','consultations','pharmacie','teleconsultation'},
        'pharmacien':  {'dashboard','pharmacie'},
        'patient':     {'dashboard','mon_dossier','mes_notifications','teleconsultation'},
    }
    allowed = perms.get(role, set())
    return [(k,h,i,l) for k,h,i,l in ALL if k in allowed]

# ================================================================
# CSS — THÈME VERT HOSPITALIER
# ================================================================
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;500;600;700;800&family=Lora:wght@400;500;600;700&display=swap');

:root{
  --grn-950:#021A0D;
  --grn-900:#042E18;
  --grn-800:#084226;
  --grn-700:#0B5734;
  --grn-600:#0E6D43;
  --grn-500:#138555;
  --grn-400:#1EA068;
  --grn-300:#39BB83;
  --grn-200:#85D4B0;
  --grn-100:#C2EBD9;
  --grn-50:#E6F7F0;
  --blu-800:#124070;
  --blu-700:#1A5590;
  --blu-500:#2E7DC8;
  --blu-400:#4D96D9;
  --blu-100:#D6EBFA;
  --blu-50:#EDF5FC;
  --amber:#D4860A;
  --amber-light:#F0A92A;
  --amber-pale:#FDF2DC;
  --red-700:#C0292A;
  --red-100:#FDEAEA;
  --red-50:#FEF5F5;
  --surface:#F2F7F5;
  --white:#FFFFFF;
  --text:#0D1F14;
  --text-mid:#2D5040;
  --text-muted:#5A7A6A;
  --border:#C8DED5;
  --border-light:#DCF0E7;
  --shadow-xs:0 1px 4px rgba(4,46,24,.06);
  --shadow-sm:0 2px 10px rgba(4,46,24,.08);
  --shadow:0 4px 20px rgba(4,46,24,.10);
  --shadow-md:0 8px 32px rgba(4,46,24,.13);
  --shadow-lg:0 16px 56px rgba(4,46,24,.18);
  --radius:12px;
  --radius-sm:8px;
  --radius-xs:6px;
  --font-display:'Lora',Georgia,serif;
  --font-body:'Nunito',system-ui,sans-serif;
  --sidebar-w:252px;
  --topbar-h:62px;
}

*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--surface);font-family:var(--font-body);color:var(--text);font-size:14px;line-height:1.65;}

.sidebar{
  position:fixed;top:0;left:0;width:var(--sidebar-w);height:100vh;
  background:linear-gradient(180deg,var(--grn-900) 0%,var(--grn-950) 100%);
  display:flex;flex-direction:column;z-index:300;
  box-shadow:4px 0 28px rgba(2,26,13,.35);
}
.sb-header{padding:22px 18px 16px;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.12);}
.sb-logo{display:flex;align-items:center;gap:12px;margin-bottom:14px;}
.sb-logo-icon{
  width:42px;height:42px;border-radius:10px;flex-shrink:0;
  background:linear-gradient(135deg,var(--grn-500),var(--grn-300));
  display:flex;align-items:center;justify-content:center;font-size:22px;
  box-shadow:0 4px 14px rgba(19,133,85,.4);
}
.sb-logo-text{flex:1;}
.sb-logo-title{color:#fff;font-family:var(--font-display);font-size:16px;font-weight:600;line-height:1.2;letter-spacing:.2px;}
.sb-logo-sub{color:rgba(255,255,255,.38);font-size:10px;letter-spacing:.9px;text-transform:uppercase;}
.sb-user{
  padding:10px 12px;background:rgba(255,255,255,.06);border-radius:var(--radius-sm);
  display:flex;align-items:center;gap:10px;border:1px solid rgba(255,255,255,.06);
}
.sb-avatar{
  width:36px;height:36px;border-radius:50%;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;
  font-family:var(--font-display);font-weight:600;font-size:14px;color:#fff;
  box-shadow:0 2px 8px rgba(0,0,0,.2);
}
.sb-user-info{flex:1;min-width:0;}
.sb-user-name{color:#fff;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sb-user-role{font-size:10.5px;color:rgba(255,255,255,.45);font-weight:400;}
.sb-nav{flex:1;padding:10px 0;overflow-y:auto;}
.sb-nav::-webkit-scrollbar{width:4px;}
.sb-nav::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:4px;}
.sb-nav ul{list-style:none;padding:0 10px;}
.sb-link{
  display:flex;align-items:center;justify-content:space-between;
  padding:9px 12px;border-radius:var(--radius-sm);
  color:rgba(255,255,255,.58);text-decoration:none;
  font-size:13px;font-weight:500;margin-bottom:2px;
  transition:all .17s ease;border:1px solid transparent;
}
.sb-link:hover{background:rgba(255,255,255,.09);color:rgba(255,255,255,.9);}
.sb-link.active{
  background:linear-gradient(90deg,rgba(30,160,104,.35),rgba(19,133,85,.2));
  color:#fff;font-weight:600;
  border-color:rgba(57,187,131,.3);
  box-shadow:inset 3px 0 0 var(--grn-300);
}
.sb-link i{font-size:15px;width:22px;flex-shrink:0;opacity:.85;}
.sb-link span{flex:1;margin-left:6px;}
.sb-badge{background:var(--amber);color:#fff;font-size:10px;padding:1px 7px;border-radius:20px;font-weight:700;}
.sb-footer{padding:12px 14px;border-top:1px solid rgba(255,255,255,.06);background:rgba(0,0,0,.12);}
.sb-footer a{
  display:flex;align-items:center;gap:8px;
  color:rgba(255,255,255,.45);text-decoration:none;font-size:13px;
  padding:8px 10px;border-radius:var(--radius-sm);transition:.15s;
}
.sb-footer a:hover{background:rgba(255,255,255,.07);color:rgba(255,255,255,.85);}

.main{margin-left:var(--sidebar-w);min-height:100vh;display:flex;flex-direction:column;}
.topbar{
  height:var(--topbar-h);background:var(--white);
  border-bottom:2px solid var(--grn-100);
  display:flex;align-items:center;justify-content:space-between;
  padding:0 28px;position:sticky;top:0;z-index:200;
  box-shadow:0 1px 6px rgba(4,46,24,.05);
}
.topbar-left{display:flex;align-items:center;gap:14px;}
.topbar-title{font-family:var(--font-display);font-size:17px;color:var(--grn-800);font-weight:600;}
.topbar-right{display:flex;align-items:center;gap:14px;}
.topbar-date{color:var(--text-muted);font-size:12.5px;}
.topbar-pill{padding:5px 13px;border-radius:20px;font-size:12px;font-weight:600;color:#fff;letter-spacing:.3px;}
.page-body{padding:28px;flex:1;}

.lt-card{
  background:var(--white);border-radius:var(--radius);
  box-shadow:var(--shadow-sm);border:1px solid var(--border-light);
  margin-bottom:22px;overflow:hidden;
}
.lt-card-header{
  padding:15px 22px;border-bottom:1px solid var(--border-light);
  display:flex;align-items:center;justify-content:space-between;background:var(--white);
}
.lt-card-title{font-family:var(--font-display);font-size:15px;color:var(--grn-800);font-weight:600;display:flex;align-items:center;gap:9px;}
.lt-card-body{padding:22px;}
.lt-card-footer{padding:12px 22px;background:var(--surface);border-top:1px solid var(--border-light);font-size:12.5px;color:var(--text-muted);}

.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px;}
.stat-card{
  background:var(--white);border-radius:var(--radius);border:1px solid var(--border-light);
  padding:20px 22px;position:relative;overflow:hidden;
  box-shadow:var(--shadow-xs);transition:transform .2s,box-shadow .2s;
}
.stat-card:hover{transform:translateY(-2px);box-shadow:var(--shadow);}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent,var(--grn-500));}
.stat-num{font-family:var(--font-display);font-size:30px;font-weight:700;color:var(--text);line-height:1;}
.stat-lbl{font-size:12.5px;color:var(--text-muted);margin-top:6px;font-weight:600;}
.stat-icon{position:absolute;right:18px;top:50%;transform:translateY(-50%);font-size:38px;opacity:.06;color:var(--accent,var(--grn-500));}

.lt-table{width:100%;border-collapse:collapse;}
.lt-table thead tr{border-bottom:2px solid var(--border-light);}
.lt-table th{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;color:var(--text-muted);padding:10px 16px;text-align:left;white-space:nowrap;background:var(--surface);}
.lt-table td{padding:12px 16px;border-bottom:1px solid var(--border-light);vertical-align:middle;}
.lt-table tbody tr:last-child td{border-bottom:none;}
.lt-table tbody tr:hover{background:var(--grn-50);}
.lt-table-responsive{overflow-x:auto;}

.lt-badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:11.5px;font-weight:600;letter-spacing:.2px;}
.lt-badge-planifie{background:var(--grn-100);color:var(--grn-700);}
.lt-badge-confirme{background:#C8EAD8;color:#0B5034;}
.lt-badge-annule{background:var(--red-100);color:var(--red-700);}
.lt-badge-effectue{background:#ECEFF1;color:#546E7A;}
.lt-badge-tele{background:#EDE7F6;color:#5E35B1;}
.lt-badge-impayee{background:var(--red-100);color:var(--red-700);}
.lt-badge-payee{background:var(--grn-100);color:var(--grn-700);}
.lt-badge-partielle{background:var(--amber-pale);color:var(--amber);}

.role-badge{display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:11.5px;font-weight:600;color:#fff;}

.lt-form-label{font-size:11.5px;font-weight:700;color:var(--text-mid);margin-bottom:5px;display:block;text-transform:uppercase;letter-spacing:.6px;}
.lt-form-control{
  width:100%;padding:9px 14px;border:1.5px solid var(--border);
  border-radius:var(--radius-sm);font-family:var(--font-body);font-size:13.5px;
  background:#fff;color:var(--text);outline:none;transition:border-color .18s,box-shadow .18s;
}
.lt-form-control:focus{border-color:var(--grn-500);box-shadow:0 0 0 3px rgba(19,133,85,.12);}
select.lt-form-control{cursor:pointer;}
textarea.lt-form-control{resize:vertical;min-height:80px;}

.lt-btn{
  display:inline-flex;align-items:center;gap:7px;padding:8px 18px;border-radius:var(--radius-sm);border:none;
  font-family:var(--font-body);font-size:13.5px;font-weight:600;cursor:pointer;text-decoration:none;transition:all .18s;white-space:nowrap;
}
.lt-btn-primary{background:var(--grn-700);color:#fff;}
.lt-btn-primary:hover{background:var(--grn-800);box-shadow:0 4px 14px rgba(11,87,52,.3);}
.lt-btn-teal{background:var(--grn-600);color:#fff;}
.lt-btn-teal:hover{background:var(--grn-700);}
.lt-btn-outline{background:transparent;color:var(--grn-700);border:1.5px solid var(--border);}
.lt-btn-outline:hover{border-color:var(--grn-400);background:var(--grn-50);}
.lt-btn-danger{background:var(--red-700);color:#fff;}
.lt-btn-danger:hover{background:#9B2020;}
.lt-btn-success{background:var(--grn-600);color:#fff;}
.lt-btn-success:hover{background:var(--grn-700);}
.lt-btn-amber{background:var(--amber);color:#fff;}
.lt-btn-amber:hover{background:#B06D08;}
.lt-btn-secondary{background:var(--blu-700);color:#fff;}
.lt-btn-secondary:hover{background:var(--blu-800);}
.lt-btn-sm{padding:6px 14px;font-size:12.5px;gap:5px;}
.lt-btn-xs{padding:4px 10px;font-size:11.5px;gap:4px;}

.lt-alert{padding:12px 16px;border-radius:var(--radius-sm);font-size:13.5px;margin-bottom:14px;display:flex;align-items:flex-start;gap:10px;}
.lt-alert i{flex-shrink:0;margin-top:2px;}
.lt-alert-success{background:var(--grn-50);color:var(--grn-700);border:1px solid var(--grn-100);}
.lt-alert-danger {background:var(--red-50);color:var(--red-700);border:1px solid var(--red-100);}
.lt-alert-info   {background:var(--blu-50);color:var(--blu-700);border:1px solid var(--blu-100);}
.lt-alert-warning{background:var(--amber-pale);color:var(--amber);border:1px solid #F0D090;}
.lt-alert button.close{margin-left:auto;background:none;border:none;font-size:16px;cursor:pointer;opacity:.6;}

.page-title{
  font-family:var(--font-display);font-size:23px;font-weight:700;
  color:var(--grn-800);margin-bottom:22px;display:flex;align-items:center;gap:12px;
}
.page-title::after{content:'';flex:1;height:2px;max-width:72px;background:linear-gradient(90deg,var(--grn-400),transparent);border-radius:2px;}

.patient-avatar{
  width:72px;height:72px;border-radius:18px;
  background:linear-gradient(135deg,var(--grn-700),var(--grn-500));
  display:flex;align-items:center;justify-content:center;
  font-family:var(--font-display);font-size:26px;font-weight:700;color:#fff;
  margin:0 auto 12px;box-shadow:0 8px 24px rgba(11,87,52,.22);
}

.info-row{display:flex;gap:6px;margin-bottom:8px;font-size:13.5px;}
.info-label{color:var(--text-muted);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;min-width:82px;padding-top:2px;}
.info-value{color:var(--text);font-weight:500;}

.login-page{
  min-height:100vh;
  background:linear-gradient(135deg,var(--grn-950) 0%,var(--grn-800) 55%,var(--grn-950) 100%);
  display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;
  padding:24px;
}
.login-bg-circles{position:absolute;inset:0;pointer-events:none;overflow:hidden;}
.login-bg-circles::before{content:'';position:absolute;width:600px;height:600px;border-radius:50%;background:radial-gradient(circle,rgba(19,133,85,.14) 0%,transparent 70%);top:-150px;left:-100px;}
.login-bg-circles::after{content:'';position:absolute;width:500px;height:500px;border-radius:50%;background:radial-gradient(circle,rgba(30,160,104,.12) 0%,transparent 70%);bottom:-120px;right:-80px;}
.login-bg-grid{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:40px 40px;}
.login-wrapper{
  display:flex;align-items:center;justify-content:center;gap:56px;
  width:100%;max-width:1140px;position:relative;z-index:1;
}
.login-services-panel{flex:1;max-width:430px;color:#fff;}
.login-services-eyebrow{
  display:inline-flex;align-items:center;gap:8px;
  padding:6px 15px;border-radius:20px;background:rgba(57,187,131,.14);
  border:1px solid rgba(57,187,131,.32);color:var(--grn-200);
  font-size:11px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;margin-bottom:20px;
}
.login-services-title{
  font-family:var(--font-display);font-size:30px;font-weight:700;color:#fff;
  line-height:1.28;margin-bottom:12px;letter-spacing:.2px;
}
.login-services-title span{color:var(--grn-300);}
.login-services-sub{
  color:rgba(255,255,255,.55);font-size:13.5px;line-height:1.7;margin-bottom:30px;max-width:400px;
}
.login-services-list{display:flex;flex-direction:column;gap:12px;}
.login-service-item{
  display:flex;align-items:flex-start;gap:14px;
  padding:13px 16px;border-radius:var(--radius-sm);
  background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.09);
  transition:.2s;
}
.login-service-item:hover{background:rgba(255,255,255,.085);border-color:rgba(57,187,131,.4);transform:translateX(4px);}
.login-service-icon{
  width:40px;height:40px;border-radius:11px;flex-shrink:0;
  background:linear-gradient(135deg,var(--grn-500),var(--grn-300));
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:15.5px;
  box-shadow:0 4px 12px rgba(19,133,85,.32);
}
.login-service-text{flex:1;min-width:0;padding-top:1px;}
.login-service-name{color:#fff;font-size:13.5px;font-weight:700;margin-bottom:2px;letter-spacing:.1px;}
.login-service-desc{color:rgba(255,255,255,.5);font-size:12px;line-height:1.5;}
.login-card{background:#fff;border-radius:20px;width:100%;max-width:440px;box-shadow:0 32px 80px rgba(0,0,0,.4);overflow:hidden;position:relative;z-index:1;border:1px solid rgba(255,255,255,.08);flex-shrink:0;}
.login-card-top{padding:36px 40px 28px;background:linear-gradient(135deg,var(--grn-800) 0%,var(--grn-600) 100%);text-align:center;position:relative;overflow:hidden;}
.login-card-top::before{content:'';position:absolute;top:-30px;right:-30px;width:140px;height:140px;border-radius:50%;background:rgba(255,255,255,.04);}
.login-card-top::after{content:'';position:absolute;bottom:-40px;left:-20px;width:120px;height:120px;border-radius:50%;background:rgba(30,160,104,.12);}
.login-logo-ring{width:76px;height:76px;border-radius:20px;margin:0 auto 16px;background:linear-gradient(135deg,var(--grn-500),var(--grn-300));display:flex;align-items:center;justify-content:center;font-size:32px;color:#fff;box-shadow:0 8px 28px rgba(0,0,0,.25);position:relative;z-index:1;}
.login-title{font-family:var(--font-display);font-size:22px;color:#fff;font-weight:700;margin-bottom:4px;position:relative;z-index:1;}
.login-sub{color:rgba(255,255,255,.55);font-size:12px;position:relative;z-index:1;line-height:1.6;}
.login-card-body{padding:32px 40px;}
.login-label{display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text-mid);margin-bottom:6px;}
.login-input{width:100%;padding:11px 14px 11px 40px;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:14px;color:var(--text);background:#fff;outline:none;transition:.18s;}
.login-input:focus{border-color:var(--grn-500);box-shadow:0 0 0 3px rgba(19,133,85,.12);}
.login-input-wrap{position:relative;}
.login-input-icon{position:absolute;left:13px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:15px;pointer-events:none;}
.login-input-eye{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:15px;cursor:pointer;}
.login-btn{width:100%;padding:12px;border:none;border-radius:var(--radius-sm);background:linear-gradient(135deg,var(--grn-700),var(--grn-600));color:#fff;font-family:var(--font-body);font-size:14px;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;transition:all .2s;box-shadow:0 4px 14px rgba(11,87,52,.3);letter-spacing:.3px;}
.login-btn:hover{background:linear-gradient(135deg,var(--grn-800),var(--grn-700));box-shadow:0 6px 20px rgba(11,87,52,.4);transform:translateY(-1px);}
.login-demo-box{margin-top:22px;padding:14px 16px;background:var(--surface);border-radius:var(--radius-sm);border:1px solid var(--border-light);}
.login-demo-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;color:var(--text-muted);margin-bottom:10px;display:flex;align-items:center;gap:6px;}
.login-demo-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:12px;}
.login-demo-item{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--radius-xs);color:var(--text-mid);}
.login-demo-item:hover{background:var(--grn-50);}
.login-demo-item i{color:var(--grn-600);font-size:13px;width:14px;text-align:center;flex-shrink:0;}
@media(max-width:980px){
  .login-wrapper{flex-direction:column;gap:32px;}
  .login-services-panel{max-width:460px;text-align:left;}
  .login-services-list{display:none;}
}

.text-muted{color:var(--text-muted);}
.text-green{color:var(--grn-600);}
.text-blue{color:var(--blu-700);}
.text-danger{color:var(--red-700);}
.text-success{color:var(--grn-600);}
.text-amber{color:var(--amber);}
.fw-600{font-weight:600;}
.fw-700{font-weight:700;}
.font-display{font-family:var(--font-display);}
.divider{height:1px;background:var(--border-light);margin:18px 0;}
.stock-lo{color:var(--red-700);font-weight:600;}
.stock-ok{color:var(--grn-600);font-weight:600;}
.d-flex{display:flex;}
.align-items-center{align-items:center;}
.justify-content-between{justify-content:space-between;}
.ms-auto{margin-left:auto;}
.gap-2{gap:8px;}
.mb-0{margin-bottom:0;}
.mb-1{margin-bottom:6px;}
.mb-2{margin-bottom:12px;}
.mb-3{margin-bottom:18px;}
.mb-4{margin-bottom:24px;}
.mt-2{margin-top:12px;}
.mt-3{margin-top:18px;}
.me-1{margin-right:4px;}
.me-2{margin-right:8px;}
.p-0{padding:0;}
.row{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;}
.col-4{grid-column:span 4;}
.col-5{grid-column:span 5;}
.col-6{grid-column:span 6;}
.col-7{grid-column:span 7;}
.col-8{grid-column:span 8;}
.col-12{grid-column:span 12;}
.col-md-3{grid-column:span 3;}
.col-md-4{grid-column:span 4;}
.col-md-6{grid-column:span 6;}
.col-md-12{grid-column:span 12;}
@media(max-width:768px){
  .col-4,.col-5,.col-6,.col-7,.col-8,.col-md-3,.col-md-4,.col-md-6{grid-column:span 12;}
  .sidebar{transform:translateX(-100%);}
  .main{margin-left:0;}
}
@media print{
  .sidebar,.topbar,.no-print{display:none!important;}
  .main{margin-left:0!important;}
}
"""

def _head(title):
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Le Tropical · {title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>{CSS}</style>
</head>'''

# ================================================================
# LAYOUT
# ================================================================
def layout(title, content, active=''):
    role     = session.get('user_role','')
    nom      = session.get('user_nom','')
    initials = ''.join(p[0].upper() for p in nom.split()[:2]) if nom else '?'
    accent   = ROLE_COLORS.get(role,'#0B5735')
    menu     = get_menu(role)

    try:
        rdv_c  = q("SELECT COUNT(*) c FROM rendez_vous WHERE date=? AND statut='planifie'",[date.today().isoformat()],one=True)['c']
        stk_c  = q("SELECT COUNT(*) c FROM medicaments WHERE stock<=stock_minimum",one=True)['c']
        fct_c  = q("SELECT COUNT(*) c FROM factures WHERE statut='impayee'",one=True)['c']
        pid    = session.get('patient_id')
        notif_c = q("SELECT COUNT(*) c FROM notifications WHERE patient_id=? AND lu=0",[pid],one=True)['c'] if pid else 0
    except: rdv_c=stk_c=fct_c=notif_c=0

    badges = {'rendez_vous':rdv_c,'mes_rdv':rdv_c,'pharmacie':stk_c,'facturation':fct_c,'mes_notifications':notif_c}

    nav_html = ''
    for k,href,icon,label in menu:
        active_cls = 'active' if active==k else ''
        b = badges.get(k,0)
        badge_html = f'<span class="sb-badge">{b}</span>' if b else ''
        nav_html += f'<li><a href="{href}" class="sb-link {active_cls}"><i class="bi {icon}"></i><span>{label}</span>{badge_html}</a></li>'

    msgs = ''
    for cat,msg in get_flashed_messages(with_categories=True):
        t  = 'success' if cat=='success' else 'danger' if cat=='error' else ('warning' if cat=='warning' else 'info')
        ic = {'success':'bi-check-circle-fill','danger':'bi-x-circle-fill','info':'bi-info-circle-fill','warning':'bi-exclamation-triangle-fill'}[t]
        msgs += (f'<div class="lt-alert lt-alert-{t}">'
                 f'<i class="bi {ic}"></i><div>{msg}</div>'
                 f'<button class="close" onclick="this.parentElement.remove()">&times;</button></div>')

    today_str = datetime.now().strftime('%a %d %b %Y').title()

    return _head(title) + f'''
<body>
<aside class="sidebar">
  <div class="sb-header">
    <div class="sb-logo">
      <div class="sb-logo-icon"><i class="fa-solid fa-house-medical" style="color:#fff"></i></div>
      <div class="sb-logo-text">
        <div class="sb-logo-title">Le Tropical</div>
        <div class="sb-logo-sub">Centre de Santé</div>
      </div>
    </div>
    <div class="sb-user">
      <div class="sb-avatar" style="background:{accent}">{initials}</div>
      <div class="sb-user-info">
        <div class="sb-user-name">{nom}</div>
        <div class="sb-user-role">{ROLE_LABELS.get(role,role)}</div>
      </div>
    </div>
  </div>
  <nav class="sb-nav"><ul>{nav_html}</ul></nav>
  <div class="sb-footer">
    <a href="/mon-compte"><i class="bi bi-gear-fill"></i> Mon compte</a>
    <a href="/logout" style="margin-top:2px"><i class="bi bi-box-arrow-right"></i> Déconnexion</a>
  </div>
</aside>
<div class="main">
  <div class="topbar">
    <div class="topbar-left">
      <span class="topbar-title">{title}</span>
    </div>
    <div class="topbar-right">
      <span class="topbar-date"><i class="bi bi-calendar3 me-1"></i>{today_str}</span>
      <span class="topbar-pill" style="background:{accent}">
        <i class="bi {ROLE_ICONS.get(role,'bi-person')} me-1"></i>{ROLE_LABELS.get(role,role)}
      </span>
    </div>
  </div>
  <div class="page-body">
    {msgs}
    {content}
  </div>
</div>
<script>
document.querySelectorAll('.sb-link').forEach(function(l){{
  l.addEventListener('click',function(){{
    document.querySelectorAll('.sb-link').forEach(function(x){{x.classList.remove('active');}});
    this.classList.add('active');
  }});
}});
</script>
</body></html>'''

# ================================================================
# LOGIN
# ================================================================
@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect('/')
    error = ''
    if request.method == 'POST':
        lv  = request.form.get('login','')
        pwd = request.form.get('password','')
        u   = q("SELECT * FROM utilisateurs WHERE login=? AND actif=1",[lv],one=True)
        if u and check_password_hash(u['mot_de_passe'],pwd):
            session['user_id']    = u['id']
            session['user_nom']   = f"{u['prenom']} {u['nom']}"
            session['user_role']  = u['role']
            session['medecin_id'] = u['medecin_id']
            session['patient_id'] = u['patient_id']
            flash(f'Bienvenue, {u["prenom"]} ! Connexion réussie.','success')
            return redirect('/')
        error = '<div class="lt-alert lt-alert-danger"><i class="bi bi-x-circle-fill"></i><div>Identifiant ou mot de passe incorrect.</div></div>'

    demo_items = [
        ('fa-solid fa-shield-halved','admin','admin123'),
        ('fa-solid fa-headset','accueil','accueil123'),
        ('fa-solid fa-user-doctor','docteur','medecin123'),
        ('fa-solid fa-pills','pharmacien','pharma123'),
        ('fa-solid fa-user','patient1','patient123'),
    ]
    demo_html = ''.join(
        f'<div class="login-demo-item"><i class="{ico}"></i><div><span style="font-weight:700;color:var(--grn-700)">{lg}</span> / <span style="color:var(--text-muted)">{pw}</span></div></div>'
        for ico,lg,pw in demo_items)

    services_items = [
        ('fa-solid fa-users','Gestion des patients','Dossiers médicaux centralisés et historique complet.'),
        ('fa-solid fa-calendar-check','Rendez-vous &amp; planification','Prise et suivi des rendez-vous en temps réel.'),
        ('fa-solid fa-stethoscope','Consultations médicales','Diagnostics, notes cliniques et suivi des patients.'),
        ('fa-solid fa-video','Téléconsultation','Consultations à distance par session vidéo sécurisée.'),
        ('fa-solid fa-prescription-bottle-medical','Ordonnances &amp; pharmacie','Prescriptions numériques et gestion des stocks.'),
        ('fa-solid fa-file-invoice-dollar','Facturation &amp; assurances','Facturation automatisée et prise en charge assurance.'),
    ]
    services_html = ''.join(f'''<div class="login-service-item">
        <div class="login-service-icon"><i class="{ico}"></i></div>
        <div class="login-service-text"><div class="login-service-name">{name}</div><div class="login-service-desc">{desc}</div></div>
      </div>''' for ico,name,desc in services_items)

    html  = _head('Connexion')
    html += f'''<body><div class="login-page"><div class="login-bg-circles"></div><div class="login-bg-grid"></div>
<div class="login-wrapper">
  <div class="login-services-panel">
    <span class="login-services-eyebrow"><i class="fa-solid fa-house-medical"></i> Centre de Santé Le Tropical</span>
    <div class="login-services-title">La santé de vos patients,<br><span>pilotée simplement.</span></div>
    <div class="login-services-sub">SGRDMS réunit en une seule plateforme tous les services nécessaires à la gestion quotidienne du centre de santé, pour le personnel comme pour les patients.</div>
    <div class="login-services-list">{services_html}</div>
  </div>
  <div class="login-card">
  <div class="login-card-top">
    <div class="login-logo-ring"><i class="fa-solid fa-house-chimney-medical"></i></div>
    <div class="login-title">Le Tropical</div>
    <div class="login-sub">Centre de Santé Communautaire<br>UIDT &middot; Système de Gestion Médicale &middot; 2026</div>
  </div>
  <div class="login-card-body">'''
    html += error
    html += '''<form method="POST" style="margin-bottom:0">
  <div class="mb-3">
    <label class="login-label">Identifiant</label>
    <div class="login-input-wrap"><i class="bi bi-person-fill login-input-icon"></i>
      <input type="text" name="login" class="login-input" placeholder="Votre identifiant" required autofocus></div>
  </div>
  <div class="mb-4">
    <label class="login-label">Mot de passe</label>
    <div class="login-input-wrap"><i class="bi bi-lock-fill login-input-icon"></i>
      <input type="password" name="password" id="pwd" class="login-input" placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;" required>
      <i class="bi bi-eye login-input-eye" id="eye_icon" onclick="togglePwd()"></i></div>
  </div>
  <button type="submit" class="login-btn"><i class="bi bi-box-arrow-in-right"></i> Se connecter</button>
</form>
<div class="login-demo-box">
  <div class="login-demo-title"><i class="bi bi-info-circle" style="color:var(--grn-400)"></i> Comptes de démonstration</div>
  <div class="login-demo-grid">'''
    html += demo_html
    html += '''</div></div></div></div></div></div>
<script>function togglePwd(){var p=document.getElementById('pwd'),e=document.getElementById('eye_icon');if(p.type==='password'){p.type='text';e.className='bi bi-eye-slash login-input-eye';}else{p.type='password';e.className='bi bi-eye login-input-eye';}}</script>
</body></html>'''
    return html

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

# ================================================================
# DASHBOARD
# ================================================================
@app.route('/')
@login_required
def dashboard():
    role = session.get('user_role','')

    if role == 'patient':
        pid  = session.get('patient_id')
        if not pid: return redirect('/mon-dossier')
        p    = q("SELECT * FROM patients WHERE id=?", [pid], one=True)
        rdvs = q("""SELECT r.*,m.nom||' '||m.prenom med FROM rendez_vous r
                    JOIN medecins m ON r.medecin_id=m.id
                    WHERE r.patient_id=? ORDER BY r.date DESC LIMIT 5""",[pid])
        notifs = q("SELECT * FROM notifications WHERE patient_id=? AND lu=0 ORDER BY created_at DESC LIMIT 3",[pid])
        notif_html = ''
        if notifs:
            notif_html = '<div class="lt-alert lt-alert-info"><i class="bi bi-bell-fill"></i><div><b>Nouveaux messages :</b> '
            notif_html += ' · '.join(n['titre'] for n in notifs)
            notif_html += f' <a href="/mes-notifications" class="lt-btn lt-btn-sm lt-btn-outline" style="margin-left:8px">Voir</a></div></div>'
        rdv_rows = ''.join(f'''<tr>
            <td>{r["date"]} <span class="text-muted">{r["heure"]}</span></td>
            <td>Dr. {r["med"]}</td><td>{badge(r["statut"])}</td><td>{r["motif"] or "—"}</td>
        </tr>''' for r in rdvs) or '<tr><td colspan="4" class="text-muted" style="padding:20px;text-align:center">Aucun rendez-vous</td></tr>'
        content = f'''
<div class="page-title"><i class="bi bi-person-heart"></i> Mon Espace Patient</div>
{notif_html}
<div style="display:grid;grid-template-columns:280px 1fr;gap:20px">
  <div class="lt-card">
    <div class="lt-card-body" style="text-align:center">
      <div class="patient-avatar">{p["nom"][0].upper() if p else "?"}</div>
      <div class="font-display" style="font-size:18px;font-weight:600;color:var(--grn-800)">{p["prenom"]} {p["nom"]}</div>
      <span class="lt-badge lt-badge-planifie" style="margin:6px auto 16px;display:inline-flex">{p["num_dossier"]}</span>
      <div class="divider"></div>
      <div class="info-row"><span class="info-label">Sexe</span><span class="info-value">{p["sexe"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Naissance</span><span class="info-value">{p["date_naissance"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Téléphone</span><span class="info-value">{p["telephone"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Gr. sanguin</span><span class="info-value fw-700 text-danger">{p["groupe_sanguin"] or "NC"}</span></div>
      {f'<div class="lt-alert lt-alert-warning mt-2" style="font-size:12.5px"><i class="bi bi-exclamation-triangle-fill"></i><div><b>Allergies:</b> {p["allergie"]}</div></div>' if p and p["allergie"] else ""}
    </div>
  </div>
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-calendar-check-fill"></i>Mes rendez-vous récents</span></div>
    <div class="lt-table-responsive">
      <table class="lt-table">
        <thead><tr><th>Date</th><th>Médecin</th><th>Statut</th><th>Motif</th></tr></thead>
        <tbody>{rdv_rows}</tbody>
      </table>
    </div>
    <div class="lt-card-footer"><small class="text-muted"><i class="bi bi-info-circle me-1"></i>Les rendez-vous sont créés par le médecin ou l'accueil.</small></div>
  </div>
</div>'''
        return layout('Mon Espace Patient', content, 'dashboard')

    if role == 'medecin':
        mid  = session.get('medecin_id')
        rdvs = q("SELECT COUNT(*) c FROM rendez_vous WHERE medecin_id=? AND date=? AND statut='planifie'",[mid, date.today().isoformat()],one=True)['c'] if mid else 0
        total_consult = q("SELECT COUNT(*) c FROM consultations c JOIN rendez_vous r ON c.rdv_id=r.id WHERE r.medecin_id=?",[mid],one=True)['c'] if mid else 0
        nb_patients  = q("SELECT COUNT(DISTINCT patient_id) c FROM rendez_vous WHERE medecin_id=?",[mid],one=True)['c'] if mid else 0
        prochains = q("""SELECT r.*,p.nom||' '||p.prenom pat,p.num_dossier nd
                         FROM rendez_vous r JOIN patients p ON r.patient_id=p.id
                         WHERE r.medecin_id=? AND r.statut IN ('planifie','confirme')
                         ORDER BY r.date,r.heure LIMIT 6""",[mid]) if mid else []
        rdv_rows2 = ''.join(f'''<tr>
            <td><b>{r["date"]}</b> {r["heure"]}</td>
            <td>{r["pat"]}<br><small class="text-muted">{r["nd"]}</small></td>
            <td>{badge(r["statut"])}</td><td>{r["motif"] or "—"}</td>
            <td><a href="/consultations/new?rdv_id={r["id"]}" class="lt-btn lt-btn-success lt-btn-xs"><i class="bi bi-clipboard2-plus"></i></a></td>
        </tr>''' for r in prochains) or '<tr><td colspan="5" class="text-muted" style="padding:20px;text-align:center">Aucun rendez-vous à venir</td></tr>'
        content = f'''
<div class="page-title"><i class="bi bi-heart-pulse-fill"></i> Tableau de bord Médecin</div>
<div class="stat-grid" style="grid-template-columns:repeat(3,1fr)">
  <div class="stat-card" style="--accent:var(--grn-500)"><div class="stat-num">{rdvs}</div><div class="stat-lbl">RDV aujourd\'hui</div><i class="bi bi-calendar-check-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--blu-500)"><div class="stat-num">{total_consult}</div><div class="stat-lbl">Consultations totales</div><i class="bi bi-clipboard2-pulse-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--amber)"><div class="stat-num">{nb_patients}</div><div class="stat-lbl">Patients suivis</div><i class="bi bi-people-fill stat-icon"></i></div>
</div>
<div style="display:grid;grid-template-columns:1fr 260px;gap:20px">
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-calendar-heart-fill"></i> Prochains rendez-vous</span>
      <a href="/mes-rdv" class="lt-btn lt-btn-outline lt-btn-sm">Voir tout</a></div>
    <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date/Heure</th><th>Patient</th><th>Statut</th><th>Motif</th><th>Action</th></tr></thead><tbody>{rdv_rows2}</tbody></table></div>
  </div>
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-lightning-fill text-amber"></i> Actions rapides</span></div>
    <div class="lt-card-body" style="display:grid;gap:8px">
      <a href="/rendez-vous/new" class="lt-btn lt-btn-primary"><i class="bi bi-calendar-plus-fill"></i> Nouveau RDV</a>
      <a href="/consultations/new" class="lt-btn lt-btn-outline"><i class="bi bi-clipboard2-plus-fill"></i> Nouvelle consultation</a>
      <a href="/patients" class="lt-btn lt-btn-outline"><i class="bi bi-people-fill"></i> Voir les patients</a>
      <a href="/pharmacie" class="lt-btn lt-btn-outline"><i class="bi bi-bag-heart-fill"></i> Pharmacie</a>
    </div>
  </div>
</div>'''
        return layout('Tableau de bord', content, 'dashboard')

    if role == 'pharmacien':
        stk_lo = q("SELECT * FROM medicaments WHERE stock<=stock_minimum ORDER BY stock LIMIT 8")
        nb_med = q("SELECT COUNT(*) c FROM medicaments",one=True)['c']
        val_stock = q("SELECT SUM(stock*prix_unitaire) v FROM medicaments",one=True)['v'] or 0
        lo_rows = ''.join(f'''<tr><td><b>{m["nom"]}</b></td>
            <td class="stock-lo"><i class="bi bi-exclamation-triangle me-1"></i>{m["stock"]}</td>
            <td class="text-muted">{m["stock_minimum"]}</td>
            <td><a href="/pharmacie/{m["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs">Gérer</a></td>
        </tr>''' for m in stk_lo) or '<tr><td colspan="4" class="text-muted" style="padding:16px;text-align:center"><i class="bi bi-check-circle me-1 text-success"></i>Tous les stocks sont OK</td></tr>'
        content = f'''
<div class="page-title"><i class="bi bi-bag-heart-fill"></i> Tableau de bord Pharmacien</div>
<div class="stat-grid" style="grid-template-columns:repeat(3,1fr)">
  <div class="stat-card" style="--accent:var(--grn-500)"><div class="stat-num">{nb_med}</div><div class="stat-lbl">Médicaments référencés</div><i class="bi bi-capsule stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--red-700)"><div class="stat-num">{len(stk_lo)}</div><div class="stat-lbl">En rupture / stock bas</div><i class="bi bi-exclamation-triangle-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--amber)"><div class="stat-num" style="font-size:20px">{fcfa(val_stock)}</div><div class="stat-lbl">Valeur du stock</div><i class="bi bi-cash stat-icon"></i></div>
</div>
<div class="lt-card">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-exclamation-triangle-fill text-danger"></i> Alertes stock</span>
    <a href="/pharmacie" class="lt-btn lt-btn-primary lt-btn-sm"><i class="bi bi-bag-heart"></i> Gérer la pharmacie</a></div>
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Médicament</th><th>Stock actuel</th><th>Stock min.</th><th>Action</th></tr></thead><tbody>{lo_rows}</tbody></table></div>
</div>'''
        return layout('Tableau de bord', content, 'dashboard')

    # Admin / Accueil
    nb_patients   = q("SELECT COUNT(*) c FROM patients",one=True)['c']
    nb_medecins   = q("SELECT COUNT(*) c FROM medecins",one=True)['c']
    rdv_today     = q("SELECT COUNT(*) c FROM rendez_vous WHERE date=?",[date.today().isoformat()],one=True)['c']
    nb_consults   = q("SELECT COUNT(*) c FROM consultations",one=True)['c']
    fact_impayees = q("SELECT COUNT(*) c FROM factures WHERE statut='impayee'",one=True)['c']
    stock_alert   = q("SELECT COUNT(*) c FROM medicaments WHERE stock<=stock_minimum",one=True)['c']
    montant_imp   = q("SELECT SUM(montant_patient) v FROM factures WHERE statut='impayee'",one=True)['v'] or 0
    rdvs = q("""SELECT r.id,r.date,r.heure,r.statut,r.motif,p.nom||' '||p.prenom pat, m.nom||' '||m.prenom med
                FROM rendez_vous r JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id
                ORDER BY r.date DESC,r.heure DESC LIMIT 7""")
    rdv_rows = ''.join(f'''<tr>
        <td><b>{r["date"]}</b> <span class="text-muted">{r["heure"]}</span></td>
        <td>{r["pat"]}</td><td>Dr. {r["med"]}</td>
        <td>{badge(r["statut"])}</td><td><small class="text-muted">{r["motif"] or "—"}</small></td>
    </tr>''' for r in rdvs) or '<tr><td colspan="5" class="text-muted" style="text-align:center;padding:20px">Aucun rendez-vous</td></tr>'
    meds_lo = q("SELECT nom,stock,stock_minimum FROM medicaments WHERE stock<=stock_minimum LIMIT 5")
    med_rows = ''.join(f'<tr><td>{m["nom"]}</td><td class="stock-lo">{m["stock"]}</td><td class="text-muted">{m["stock_minimum"]}</td></tr>' for m in meds_lo) or '<tr><td colspan="3" class="text-muted text-center" style="padding:14px"><i class="bi bi-check-circle me-1 stock-ok"></i>Stocks OK</td></tr>'
    content = f'''
<div class="page-title"><i class="bi bi-grid-fill"></i> Tableau de bord</div>
<div class="stat-grid">
  <div class="stat-card" style="--accent:var(--grn-500)"><div class="stat-num">{nb_patients}</div><div class="stat-lbl">Patients</div><i class="bi bi-people-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--grn-600)"><div class="stat-num">{nb_medecins}</div><div class="stat-lbl">Médecins</div><i class="bi bi-person-badge-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:#5E35B1"><div class="stat-num">{rdv_today}</div><div class="stat-lbl">RDV aujourd\'hui</div><i class="bi bi-calendar-check-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--blu-500)"><div class="stat-num">{nb_consults}</div><div class="stat-lbl">Consultations</div><i class="bi bi-clipboard2-pulse-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--red-700)"><div class="stat-num">{fact_impayees}</div><div class="stat-lbl">Factures impayées</div><i class="bi bi-receipt-cutoff stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--amber)"><div class="stat-num">{stock_alert}</div><div class="stat-lbl">Alertes stock</div><i class="bi bi-capsule stat-icon"></i></div>
</div>
<div style="display:grid;grid-template-columns:1fr 320px;gap:20px">
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-calendar-check-fill"></i> Derniers Rendez-vous</span>
      <a href="/rendez-vous" class="lt-btn lt-btn-outline lt-btn-sm">Voir tout</a></div>
    <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date</th><th>Patient</th><th>Médecin</th><th>Statut</th><th>Motif</th></tr></thead><tbody>{rdv_rows}</tbody></table></div>
  </div>
  <div>
    <div class="lt-card">
      <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-exclamation-triangle-fill" style="color:var(--red-700)"></i> Alertes Stock</span></div>
      <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Médicament</th><th>Stock</th><th>Min.</th></tr></thead><tbody>{med_rows}</tbody></table></div>
      <div class="lt-card-footer"><a href="/pharmacie" class="lt-btn lt-btn-outline lt-btn-sm">Gérer la pharmacie</a></div>
    </div>
    <div class="lt-card">
      <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-lightning-fill text-amber"></i> Actions rapides</span></div>
      <div class="lt-card-body" style="display:grid;gap:8px">
        <a href="/patients/new" class="lt-btn lt-btn-outline"><i class="bi bi-person-plus-fill"></i> Nouveau patient</a>
        <a href="/rendez-vous/new" class="lt-btn lt-btn-outline"><i class="bi bi-calendar-plus-fill"></i> Nouveau RDV</a>
        <a href="/consultations/new" class="lt-btn lt-btn-outline"><i class="bi bi-clipboard2-plus-fill"></i> Nouvelle consultation</a>
        <div class="divider" style="margin:4px 0"></div>
        <div style="text-align:center">
          <div class="text-muted" style="font-size:12px;margin-bottom:4px">Factures impayées</div>
          <div class="font-display text-danger" style="font-size:20px;font-weight:700">{fcfa(montant_imp)}</div>
        </div>
      </div>
    </div>
  </div>
</div>'''
    return layout('Tableau de bord', content, 'dashboard')

# ================================================================
# GESTION COMPTES (ADMIN)
# ================================================================
@app.route('/utilisateurs')
@login_required
@roles_allowed('admin')
def utilisateurs():
    users = q("""SELECT u.*,m.nom||' '||m.prenom AS medecin_nom,p.nom||' '||p.prenom AS patient_nom
                 FROM utilisateurs u LEFT JOIN medecins m ON u.medecin_id=m.id LEFT JOIN patients p ON u.patient_id=p.id
                 ORDER BY u.role,u.nom""")
    medecins_list = q("SELECT id,nom,prenom FROM medecins ORDER BY nom")
    patients_list = q("SELECT id,nom,prenom,num_dossier FROM patients ORDER BY nom")
    med_opts  = '<option value="">— Aucun —</option>'+''.join(f'<option value="{m["id"]}">Dr. {m["nom"]} {m["prenom"]}</option>' for m in medecins_list)
    pat_opts  = '<option value="">— Aucun —</option>'+''.join(f'<option value="{p["id"]}">{p["nom"]} {p["prenom"]} ({p["num_dossier"]})</option>' for p in patients_list)
    role_opts = ''.join(f'<option value="{k}">{v}</option>' for k,v in ROLE_LABELS.items())
    rows = ''
    for u in users:
        acc = ROLE_COLORS.get(u['role'],'#0B5735')
        rows += f'''<tr>
            <td><div style="display:flex;align-items:center;gap:10px">
              <div style="width:36px;height:36px;border-radius:9px;background:{acc};display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px;flex-shrink:0">{u["prenom"][0].upper()}{u["nom"][0].upper()}</div>
              <div><div class="fw-600">{u["prenom"]} {u["nom"]}</div><small class="text-muted">@{u["login"]}</small></div>
            </div></td>
            <td><span class="role-badge" style="background:{acc}"><i class="bi {ROLE_ICONS.get(u['role'],'bi-person')}"></i>{ROLE_LABELS.get(u['role'],u['role'])}</span></td>
            <td>{u["medecin_nom"] or u["patient_nom"] or '<span class="text-muted">—</span>'}</td>
            <td>{"<span class='lt-badge lt-badge-confirme'>Actif</span>" if u["actif"] else "<span class='lt-badge lt-badge-annule'>Inactif</span>"}</td>
            <td>{u["created_at"][:10] if u["created_at"] else "—"}</td>
            <td style="display:flex;gap:6px">
              <a href="/utilisateurs/{u["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a>
              {"" if u["login"]=="admin" else f'<form method="POST" action="/utilisateurs/{u["id"]}/toggle" style="display:inline"><button class="lt-btn lt-btn-xs" style="background:'+('#fdeaea;color:var(--red-700)' if u['actif'] else 'var(--grn-50);color:var(--grn-700)')+';border:1px solid '+('#f5c0c0' if u['actif'] else 'var(--grn-100)')+'">'+('Désactiver' if u['actif'] else 'Activer')+'</button></form>'}
            </td>
        </tr>'''
    content = f'''
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
  <div class="page-title" style="margin:0"><i class="bi bi-person-lines-fill"></i> Gestion des Comptes</div>
  <button class="lt-btn lt-btn-primary" onclick="document.getElementById('modalUser').style.display='flex'"><i class="bi bi-person-plus-fill"></i> Nouveau compte</button>
</div>
<div class="lt-card"><div class="lt-table-responsive">
  <table class="lt-table"><thead><tr><th>Utilisateur</th><th>Rôle</th><th>Lié à</th><th>Statut</th><th>Créé le</th><th>Actions</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div></div>
<div id="modalUser" style="display:none;position:fixed;inset:0;background:rgba(2,26,13,.55);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:16px;width:100%;max-width:520px;max-height:90vh;overflow-y:auto;box-shadow:var(--shadow-lg)">
    <div style="padding:20px 24px;border-bottom:1px solid var(--border-light);display:flex;align-items:center;justify-content:space-between">
      <span class="font-display" style="font-size:16px;font-weight:600;color:var(--grn-800)"><i class="bi bi-person-plus-fill me-2"></i>Nouveau compte</span>
      <button onclick="document.getElementById('modalUser').style.display='none'" style="background:none;border:none;font-size:22px;cursor:pointer;color:#888">&times;</button>
    </div>
    <form method="POST" action="/utilisateurs/new" style="padding:24px">
      <div class="row">
        <div class="col-6 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" required></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Prénom *</label><input type="text" name="prenom" class="lt-form-control" required></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Identifiant *</label><input type="text" name="login" class="lt-form-control" required></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Mot de passe *</label><input type="password" name="password" class="lt-form-control" required minlength="6"></div>
        <div class="col-12 mb-3"><label class="lt-form-label">Rôle *</label><select name="role" class="lt-form-control" required>{role_opts}</select></div>
        <div class="col-12 mb-3"><label class="lt-form-label">Lier à un médecin</label><select name="medecin_id" class="lt-form-control">{med_opts}</select></div>
        <div class="col-12 mb-3"><label class="lt-form-label">Lier à un patient</label><select name="patient_id" class="lt-form-control">{pat_opts}</select></div>
      </div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Créer</button>
        <button type="button" onclick="document.getElementById('modalUser').style.display='none'" class="lt-btn lt-btn-outline">Annuler</button></div>
    </form>
  </div>
</div>'''
    return layout('Gestion des Comptes', content, 'utilisateurs')

@app.route('/utilisateurs/new', methods=['POST'])
@login_required
@roles_allowed('admin')
def utilisateur_new():
    f = request.form
    existing = q("SELECT id FROM utilisateurs WHERE login=?",[f['login']],one=True)
    if existing: flash('Cet identifiant est déjà utilisé.','error'); return redirect('/utilisateurs')
    ex("INSERT INTO utilisateurs(nom,prenom,login,mot_de_passe,role,medecin_id,patient_id) VALUES(?,?,?,?,?,?,?)",
       [f['nom'],f['prenom'],f['login'],generate_password_hash(f['password']),
        f.get('role'),f.get('medecin_id') or None,f.get('patient_id') or None])
    flash(f'Compte @{f["login"]} créé.','success')
    return redirect('/utilisateurs')

@app.route('/utilisateurs/<int:uid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin')
def utilisateur_edit(uid):
    u = q("SELECT * FROM utilisateurs WHERE id=?",[uid],one=True)
    if not u: flash('Compte introuvable.','error'); return redirect('/utilisateurs')
    medecins_list = q("SELECT id,nom,prenom FROM medecins ORDER BY nom")
    patients_list = q("SELECT id,nom,prenom,num_dossier FROM patients ORDER BY nom")
    if request.method == 'POST':
        f = request.form
        args = [f['nom'],f['prenom'],f.get('role'),f.get('medecin_id') or None,f.get('patient_id') or None]
        if f.get('password'):
            ex("UPDATE utilisateurs SET nom=?,prenom=?,role=?,medecin_id=?,patient_id=?,mot_de_passe=? WHERE id=?",args+[generate_password_hash(f['password']),uid])
        else:
            ex("UPDATE utilisateurs SET nom=?,prenom=?,role=?,medecin_id=?,patient_id=? WHERE id=?",args+[uid])
        flash('Compte mis à jour.','success'); return redirect('/utilisateurs')
    role_opts = ''.join(f'<option value="{k}" {"selected" if u["role"]==k else ""}>{v}</option>' for k,v in ROLE_LABELS.items())
    med_opts  = '<option value="">— Aucun —</option>'+''.join(f'<option value="{m["id"]}" {"selected" if u["medecin_id"]==m["id"] else ""}>Dr. {m["nom"]} {m["prenom"]}</option>' for m in medecins_list)
    pat_opts  = '<option value="">— Aucun —</option>'+''.join(f'<option value="{p["id"]}" {"selected" if u["patient_id"]==p["id"] else ""}>{p["nom"]} {p["prenom"]} ({p["num_dossier"]})</option>' for p in patients_list)
    content = f'''
<div class="mb-3"><a href="/utilisateurs" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:560px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-pencil-square"></i> Modifier @{u["login"]}</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="row">
      <div class="col-6 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" value="{u["nom"]}" required></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Prénom *</label><input type="text" name="prenom" class="lt-form-control" value="{u["prenom"]}" required></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Rôle</label><select name="role" class="lt-form-control">{role_opts}</select></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Lier à un médecin</label><select name="medecin_id" class="lt-form-control">{med_opts}</select></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Lier à un patient</label><select name="patient_id" class="lt-form-control">{pat_opts}</select></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Nouveau mot de passe (vide = inchangé)</label><input type="password" name="password" class="lt-form-control" minlength="6" placeholder="••••••••"></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Mettre à jour</button>
      <a href="/utilisateurs" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Modifier Compte', content, 'utilisateurs')

@app.route('/utilisateurs/<int:uid>/toggle', methods=['POST'])
@login_required
@roles_allowed('admin')
def utilisateur_toggle(uid):
    u = q("SELECT actif FROM utilisateurs WHERE id=?",[uid],one=True)
    if u: ex("UPDATE utilisateurs SET actif=? WHERE id=?",[0 if u['actif'] else 1, uid]); flash('Statut mis à jour.','success')
    return redirect('/utilisateurs')

# ================================================================
# MON COMPTE
# ================================================================
@app.route('/mon-compte', methods=['GET','POST'])
@login_required
def mon_compte():
    uid = session['user_id']
    u   = q("SELECT * FROM utilisateurs WHERE id=?",[uid],one=True)
    if request.method == 'POST':
        f = request.form
        if f.get('new_password'):
            if not check_password_hash(u['mot_de_passe'], f.get('old_password','')):
                flash('Mot de passe actuel incorrect.','error')
            elif f['new_password'] != f.get('confirm_password',''):
                flash('Les mots de passe ne correspondent pas.','error')
            elif len(f['new_password']) < 6:
                flash('Le mot de passe doit avoir au moins 6 caractères.','error')
            else:
                ex("UPDATE utilisateurs SET mot_de_passe=? WHERE id=?",[generate_password_hash(f['new_password']),uid])
                flash('Mot de passe modifié avec succès.','success')
    content = f'''
<div class="page-title"><i class="bi bi-gear-fill"></i> Mon Compte</div>
<div style="display:grid;grid-template-columns:300px 1fr;gap:20px">
  <div class="lt-card">
    <div class="lt-card-body" style="text-align:center;padding:30px 20px">
      <div style="width:72px;height:72px;border-radius:18px;background:{ROLE_COLORS.get(u["role"],"#0B5735")};
           display:flex;align-items:center;justify-content:center;margin:0 auto 14px;
           font-family:var(--font-display);font-size:26px;font-weight:700;color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.15)">
        {u["prenom"][0].upper()}{u["nom"][0].upper()}
      </div>
      <div class="font-display" style="font-size:18px;font-weight:600;color:var(--grn-800)">{u["prenom"]} {u["nom"]}</div>
      <div class="text-muted mb-2">@{u["login"]}</div>
      <span class="role-badge" style="background:{ROLE_COLORS.get(u["role"],"#0B5735")}">
        <i class="bi {ROLE_ICONS.get(u["role"],"bi-person")}"></i> {ROLE_LABELS.get(u["role"],u["role"])}
      </span>
    </div>
  </div>
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-lock-fill"></i> Changer le mot de passe</span></div>
    <div class="lt-card-body"><form method="POST" style="max-width:400px">
      <div class="mb-3"><label class="lt-form-label">Mot de passe actuel *</label><input type="password" name="old_password" class="lt-form-control" required placeholder="••••••••"></div>
      <div class="mb-3"><label class="lt-form-label">Nouveau mot de passe *</label><input type="password" name="new_password" class="lt-form-control" required minlength="6" placeholder="••••••••"></div>
      <div class="mb-3"><label class="lt-form-label">Confirmer *</label><input type="password" name="confirm_password" class="lt-form-control" required placeholder="••••••••"></div>
      <button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Enregistrer</button>
    </form></div>
  </div>
</div>'''
    return layout('Mon Compte', content)

# ================================================================
# NOTIFICATIONS PATIENT
# ================================================================
@app.route('/mes-notifications')
@login_required
@roles_allowed('patient')
def mes_notifications():
    pid = session.get('patient_id')
    if not pid: return redirect('/')
    notifs = q("SELECT * FROM notifications WHERE patient_id=? ORDER BY created_at DESC",[pid])
    ex("UPDATE notifications SET lu=1 WHERE patient_id=?",[pid])
    rows = ''.join(f'''<tr style="background:{'var(--grn-50)' if not n['lu'] else ''}">
        <td>
          <div style="display:flex;align-items:flex-start;gap:12px">
            <div style="width:36px;height:36px;border-radius:50%;background:var(--grn-100);display:flex;align-items:center;justify-content:center;flex-shrink:0">
              <i class="bi bi-bell-fill" style="color:var(--grn-600)"></i>
            </div>
            <div><div class="fw-600">{n["titre"]}</div><div style="font-size:13px;color:var(--text-mid);margin-top:4px">{n["message"]}</div></div>
          </div>
        </td>
        <td style="white-space:nowrap;color:var(--text-muted);font-size:12.5px">{n["created_at"][:16] if n["created_at"] else "—"}</td>
        <td>{"<span class='lt-badge lt-badge-planifie'>Nouveau</span>" if not n["lu"] else "<span class='lt-badge lt-badge-effectue'>Lu</span>"}</td>
    </tr>''' for n in notifs) or '<tr><td colspan="3" class="text-muted" style="text-align:center;padding:28px">Aucun message</td></tr>'
    content = f'''
<div class="page-title"><i class="bi bi-bell-fill"></i> Mes Messages</div>
<div class="lt-card">
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Message</th><th>Date</th><th>Statut</th></tr></thead><tbody>{rows}</tbody></table></div>
  <div class="lt-card-footer">{len(notifs)} message(s)</div>
</div>'''
    return layout('Mes Messages', content, 'mes_notifications')

# ================================================================
# MON DOSSIER (patient)
# ================================================================
@app.route('/mon-dossier')
@login_required
@roles_allowed('patient')
def mon_dossier():
    pid = session.get('patient_id')
    if not pid: flash('Aucun dossier lié à ce compte.','error'); return redirect('/')
    p    = q("SELECT * FROM patients WHERE id=?",[pid],one=True)
    rdvs = q("""SELECT r.*,m.nom||' '||m.prenom med,s.nom svc
                FROM rendez_vous r JOIN medecins m ON r.medecin_id=m.id
                LEFT JOIN services s ON m.service_id=s.id
                WHERE r.patient_id=? ORDER BY r.date DESC""",[pid])
    consults = q("""SELECT c.*,r.date rd,r.heure rh,m.nom||' '||m.prenom med,o.id oid
                    FROM consultations c JOIN rendez_vous r ON c.rdv_id=r.id
                    JOIN medecins m ON r.medecin_id=m.id
                    LEFT JOIN ordonnances o ON o.consultation_id=c.id
                    WHERE r.patient_id=? ORDER BY c.date DESC""",[pid])
    age = ''
    if p and p['date_naissance']:
        try: age = f" · {(date.today()-date.fromisoformat(p['date_naissance'])).days//365} ans"
        except: pass
    rdv_rows = ''.join(f'''<tr>
        <td><b>{r["date"]}</b> {r["heure"]}</td>
        <td>Dr. {r["med"]}<br><small class="text-muted">{r["svc"] or ""}</small></td>
        <td>{badge(r["statut"])}</td><td>{r["motif"] or "—"}</td>
    </tr>''' for r in rdvs) or '<tr><td colspan="4" class="text-muted" style="text-align:center;padding:20px">Aucun rendez-vous</td></tr>'
    c_rows = ''.join(f'''<tr>
        <td>{c["rd"]} {c["rh"]}</td><td>Dr. {c["med"]}</td>
        <td>{(c["diagnostic"] or "—")[:60]}</td>
        <td>{"<span class='lt-badge lt-badge-confirme'><i class='bi bi-prescription2 me-1'></i>Oui</span>" if c["oid"] else "<span class='lt-badge lt-badge-effectue'>Non</span>"}</td>
    </tr>''' for c in consults) or '<tr><td colspan="4" class="text-muted" style="text-align:center;padding:20px">Aucune consultation</td></tr>'
    content = f'''
<div class="page-title"><i class="bi bi-folder2-open"></i> Mon Dossier Médical</div>
<div style="display:grid;grid-template-columns:260px 1fr;gap:20px">
  <div class="lt-card">
    <div class="lt-card-body" style="text-align:center;padding:28px 18px">
      <div class="patient-avatar">{p["nom"][0].upper() if p else "?"}</div>
      <div class="font-display" style="font-size:17px;font-weight:700;color:var(--grn-800)">{p["prenom"]} {p["nom"]}</div>
      <span class="lt-badge lt-badge-planifie" style="margin:6px auto 16px;display:inline-flex">{p["num_dossier"]}</span>
      <div class="divider"></div>
      <div class="info-row"><span class="info-label">Sexe</span><span class="info-value">{p["sexe"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Naissance</span><span class="info-value">{p["date_naissance"] or "—"}{age}</span></div>
      <div class="info-row"><span class="info-label">Tél.</span><span class="info-value">{p["telephone"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Adresse</span><span class="info-value">{p["adresse"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Gr. sang.</span><span class="info-value fw-700 text-danger">{p["groupe_sanguin"] or "NC"}</span></div>
      {f'<div class="lt-alert lt-alert-warning mt-2" style="font-size:12.5px;text-align:left"><i class="bi bi-exclamation-triangle-fill"></i><div><b>Allergies:</b> {p["allergie"]}</div></div>' if p and p["allergie"] else ""}
    </div>
  </div>
  <div>
    <div class="lt-card mb-3">
      <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-calendar-check-fill"></i> Mes Rendez-vous ({len(rdvs)})</span></div>
      <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date / Heure</th><th>Médecin</th><th>Statut</th><th>Motif</th></tr></thead><tbody>{rdv_rows}</tbody></table></div>
      <div class="lt-card-footer"><small class="text-muted"><i class="bi bi-info-circle me-1"></i>Les rendez-vous sont planifiés par le médecin ou l'accueil.</small></div>
    </div>
    <div class="lt-card">
      <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-clipboard2-pulse-fill"></i> Mes Consultations ({len(consults)})</span></div>
      <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date</th><th>Médecin</th><th>Diagnostic</th><th>Ordonnance</th></tr></thead><tbody>{c_rows}</tbody></table></div>
    </div>
  </div>
</div>'''
    return layout('Mon Dossier', content, 'mon_dossier')

# ================================================================
# MES RDV (médecin)
# ================================================================
@app.route('/mes-rdv')
@login_required
@roles_allowed('medecin')
def mes_rdv():
    mid  = session.get('medecin_id')
    filt = request.args.get('statut','')
    cond = "r.medecin_id=?"; params = [mid]
    if filt: cond += " AND r.statut=?"; params.append(filt)
    rows = q(f"""SELECT r.*,p.nom||' '||p.prenom pat,p.num_dossier nd
                 FROM rendez_vous r JOIN patients p ON r.patient_id=p.id
                 WHERE {cond} ORDER BY r.date DESC,r.heure DESC""", params)
    s_opts = ''.join(f'<option value="{v}" {"selected" if filt==v else ""}>{l}</option>'
        for v,l in [('','Tous'),('planifie','Planifié'),('confirme','Confirmé'),('effectue','Effectué'),('annule','Annulé')])
    trs = ''.join(f'''<tr>
        <td><b>{r["date"]}</b><br><small class="text-muted">{r["heure"]}</small></td>
        <td>{r["pat"]}<br><small class="text-muted">{r["nd"]}</small></td>
        <td>{badge(r["statut"])}</td>
        <td>{"<span class='lt-badge lt-badge-tele'>Téléconsult.</span>" if r["type"]=="teleconsultation" else "Présentiel"}</td>
        <td>{r["motif"] or "—"}</td>
        <td style="display:flex;gap:4px">
          {f'<a href="/consultations/new?rdv_id={r["id"]}" class="lt-btn lt-btn-success lt-btn-xs"><i class="bi bi-clipboard2-plus"></i></a>' if r["statut"] in ("planifie","confirme") and not q("SELECT id FROM consultations WHERE rdv_id=?",[r["id"]],one=True) else ""}
        </td>
    </tr>''' for r in rows) or '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:22px">Aucun rendez-vous</td></tr>'
    content = f'''
<div class="page-title"><i class="bi bi-calendar-heart-fill"></i> Mes Rendez-vous</div>
<div class="lt-card">
  <div class="lt-card-header">
    <form method="GET" style="display:flex;gap:10px;align-items:center">
      <label class="lt-form-label" style="margin:0;white-space:nowrap">Filtrer :</label>
      <select name="statut" class="lt-form-control" style="width:180px">{s_opts}</select>
      <button class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-funnel"></i> Filtrer</button>
    </form>
    <a href="/rendez-vous/new" class="lt-btn lt-btn-primary lt-btn-sm"><i class="bi bi-calendar-plus-fill"></i> Nouveau RDV</a>
  </div>
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date / Heure</th><th>Patient</th><th>Statut</th><th>Type</th><th>Motif</th><th>Action</th></tr></thead><tbody>{trs}</tbody></table></div>
  <div class="lt-card-footer">{len(rows)} rendez-vous</div>
</div>'''
    return layout('Mes Rendez-vous', content, 'mes_rdv')

# ================================================================
# PATIENTS
# ================================================================
@app.route('/patients')
@login_required
@roles_allowed('admin','accueil','medecin')
def patients():
    search = request.args.get('q','')
    rows = q("SELECT * FROM patients WHERE nom LIKE ? OR prenom LIKE ? OR num_dossier LIKE ? OR telephone LIKE ? ORDER BY nom",[f'%{search}%']*4) if search else q("SELECT * FROM patients ORDER BY nom")
    role = session.get('user_role','')
    trs = ''.join(f'''<tr>
        <td><span class="lt-badge lt-badge-planifie">{p["num_dossier"]}</span></td>
        <td><div style="display:flex;align-items:center;gap:10px">
          <div style="width:34px;height:34px;border-radius:9px;background:var(--grn-700);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px;flex-shrink:0">{p["nom"][0].upper()}</div>
          <div><div class="fw-600">{p["nom"]} {p["prenom"]}</div><small class="text-muted">{p["telephone"] or ""}</small></div>
        </div></td>
        <td>{p["sexe"] or "—"}</td>
        <td>{p["date_naissance"] or "—"}</td>
        <td>{"<span class='fw-700 text-danger'>"+p["groupe_sanguin"]+"</span>" if p["groupe_sanguin"] else "—"}</td>
        <td style="display:flex;gap:4px">
          <a href="/patients/{p["id"]}" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-eye"></i></a>
          {f'<a href="/patients/{p["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a>' if role in ("admin","accueil") else ""}
          {f'<form method="POST" action="/patients/{p["id"]}/delete" style="display:inline" onsubmit="return confirm(\'Supprimer ?\')"><button class="lt-btn lt-btn-xs" style="background:var(--red-50);color:var(--red-700);border:1px solid var(--red-100)"><i class="bi bi-trash"></i></button></form>' if role in ("admin","accueil") else ""}
        </td>
    </tr>''' for p in rows) or '<tr><td colspan="6" style="text-align:center;padding:22px;color:var(--text-muted)">Aucun patient</td></tr>'
    content = f'''
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
  <div class="page-title" style="margin:0"><i class="bi bi-people-fill"></i> Patients</div>
  {f'<a href="/patients/new" class="lt-btn lt-btn-primary"><i class="bi bi-person-plus-fill"></i> Nouveau patient</a>' if role in ("admin","accueil") else ""}
</div>
<div class="lt-card">
  <div class="lt-card-header">
    <form method="GET" style="display:flex;gap:10px;flex:1">
      <input type="text" name="q" value="{search}" class="lt-form-control" style="max-width:400px" placeholder="Nom, prénom, N° dossier, téléphone...">
      <button class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-search"></i> Chercher</button>
      {"<a href='/patients' class='lt-btn lt-btn-outline lt-btn-sm'>✕ Réinitialiser</a>" if search else ""}
    </form>
    <span class="text-muted" style="font-size:13px">{len(rows)} patient(s)</span>
  </div>
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>N° Dossier</th><th>Patient</th><th>Sexe</th><th>Naissance</th><th>Gr. sanguin</th><th>Actions</th></tr></thead><tbody>{trs}</tbody></table></div>
</div>'''
    return layout('Patients', content, 'patients')

@app.route('/patients/new', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil')
def patient_new():
    if request.method == 'POST':
        f   = request.form
        num = gen_num_dossier()
        pid = ex("INSERT INTO patients(nom,prenom,date_naissance,sexe,telephone,email,adresse,num_dossier,groupe_sanguin,allergie) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 [f['nom'],f['prenom'],f.get('date_naissance') or None,f.get('sexe'),f.get('telephone'),f.get('email'),f.get('adresse'),num,f.get('groupe_sanguin'),f.get('allergie')])
        auto_login = gen_login(f['prenom'], f['nom'])
        auto_pwd   = gen_password(8)
        ex("INSERT INTO utilisateurs(nom,prenom,login,mot_de_passe,role,patient_id) VALUES(?,?,?,?,?,?)",
           [f['nom'],f['prenom'],auto_login,generate_password_hash(auto_pwd),'patient',pid])
        flash(f'Patient enregistré · dossier <b>{num}</b> · Compte créé : <b>{auto_login}</b> / <b>{auto_pwd}</b> (à communiquer au patient)','success')
        return redirect('/patients')
    grp_opts = ''.join(f'<option>{g}</option>' for g in ['A+','A-','B+','B-','AB+','AB-','O+','O-'])
    content = f'''
<div class="mb-3"><a href="/patients" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-alert lt-alert-info mb-3" style="max-width:740px"><i class="bi bi-info-circle-fill"></i><div>Un compte patient sera automatiquement créé avec un identifiant et un mot de passe temporaire à communiquer au patient.</div></div>
<div class="lt-card" style="max-width:740px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-person-plus-fill"></i> Nouveau Patient</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="row">
      <div class="col-6 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" required></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Prénom *</label><input type="text" name="prenom" class="lt-form-control" required></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Date de naissance</label><input type="date" name="date_naissance" class="lt-form-control"></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Sexe</label><select name="sexe" class="lt-form-control"><option value="">—</option><option value="M">Masculin</option><option value="F">Féminin</option></select></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Groupe sanguin</label><select name="groupe_sanguin" class="lt-form-control"><option value="">—</option>{grp_opts}</select></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Téléphone</label><input type="tel" name="telephone" class="lt-form-control" placeholder="+221 xx xxx xx xx"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Email</label><input type="email" name="email" class="lt-form-control"></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Adresse</label><input type="text" name="adresse" class="lt-form-control"></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Allergies connues</label><textarea name="allergie" class="lt-form-control" placeholder="Ex : pénicilline, aspirine..."></textarea></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Enregistrer &amp; Créer compte</button><a href="/patients" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Nouveau Patient', content, 'patients')

@app.route('/patients/<int:pid>')
@login_required
@roles_allowed('admin','accueil','medecin')
def patient_view(pid):
    p = q("SELECT * FROM patients WHERE id=?",[pid],one=True)
    if not p: flash('Patient introuvable.','error'); return redirect('/patients')
    role = session.get('user_role','')
    rdvs  = q("SELECT r.*,m.nom||' '||m.prenom med FROM rendez_vous r JOIN medecins m ON r.medecin_id=m.id WHERE r.patient_id=? ORDER BY r.date DESC",[pid])
    assur = q("SELECT pa.*,a.nom an,a.type FROM patient_assurance pa JOIN assurances a ON pa.assurance_id=a.id WHERE pa.patient_id=?",[pid])
    age = ''
    if p['date_naissance']:
        try: age = f" · {(date.today()-date.fromisoformat(p['date_naissance'])).days//365} ans"
        except: pass
    rdv_rows = ''.join(f'<tr><td><b>{r["date"]}</b> {r["heure"]}</td><td>Dr. {r["med"]}</td><td>{badge(r["statut"])}</td><td>{r["motif"] or "—"}</td></tr>' for r in rdvs) or '<tr><td colspan="4" class="text-muted" style="text-align:center;padding:18px">Aucun rendez-vous</td></tr>'
    ass_rows = ''.join(f'<tr><td>{a["an"]}</td><td>{a["type"]}</td><td>{a["numero_contrat"] or "—"}</td><td>{a["taux_prise_en_charge"]}%</td><td>{a["date_debut"] or "—"} → {a["date_fin"] or "—"}</td></tr>' for a in assur) or '<tr><td colspan="5" class="text-muted" style="text-align:center;padding:18px">Aucune assurance</td></tr>'
    content = f'''
<div style="display:flex;justify-content:space-between;margin-bottom:18px">
  <a href="/patients" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a>
  {f'<a href="/patients/{pid}/edit" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-pencil"></i> Modifier</a>' if role in ("admin","accueil") else ""}
</div>
<div style="display:grid;grid-template-columns:260px 1fr;gap:20px">
  <div class="lt-card">
    <div class="lt-card-body" style="text-align:center;padding:28px 18px">
      <div class="patient-avatar">{p["nom"][0].upper()}</div>
      <div class="font-display" style="font-size:17px;font-weight:700;color:var(--grn-800)">{p["prenom"]} {p["nom"]}</div>
      <span class="lt-badge lt-badge-planifie" style="margin:6px auto 16px;display:inline-flex">{p["num_dossier"]}</span>
      <div class="divider"></div>
      <div class="info-row"><span class="info-label">Sexe</span><span class="info-value">{p["sexe"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Naissance</span><span class="info-value">{p["date_naissance"] or "—"}{age}</span></div>
      <div class="info-row"><span class="info-label">Tél.</span><span class="info-value">{p["telephone"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Email</span><span class="info-value" style="font-size:12px">{p["email"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Adresse</span><span class="info-value" style="font-size:12px">{p["adresse"] or "—"}</span></div>
      <div class="info-row"><span class="info-label">Gr. sang.</span><span class="info-value fw-700 text-danger">{p["groupe_sanguin"] or "NC"}</span></div>
      {f'<div class="lt-alert lt-alert-warning mt-2" style="font-size:12.5px;text-align:left"><i class="bi bi-exclamation-triangle-fill"></i><div><b>Allergies:</b> {p["allergie"]}</div></div>' if p["allergie"] else ""}
      <div class="divider"></div>
      <a href="/rendez-vous/new?patient_id={pid}" class="lt-btn lt-btn-primary" style="width:100%;justify-content:center"><i class="bi bi-calendar-plus-fill"></i> Nouveau RDV</a>
    </div>
  </div>
  <div>
    <div class="lt-card mb-3">
      <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-calendar-check-fill"></i> Rendez-vous ({len(rdvs)})</span></div>
      <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date/Heure</th><th>Médecin</th><th>Statut</th><th>Motif</th></tr></thead><tbody>{rdv_rows}</tbody></table></div>
    </div>
    <div class="lt-card">
      <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-shield-fill-check"></i> Assurances</span>
        {f'<a href="/assurances/patient/{pid}/add" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-plus"></i> Ajouter</a>' if role in ("admin","accueil") else ""}
      </div>
      <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Assurance</th><th>Type</th><th>N° Contrat</th><th>Taux</th><th>Validité</th></tr></thead><tbody>{ass_rows}</tbody></table></div>
    </div>
  </div>
</div>'''
    return layout(f'Dossier · {p["prenom"]} {p["nom"]}', content, 'patients')

@app.route('/patients/<int:pid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil')
def patient_edit(pid):
    p = q("SELECT * FROM patients WHERE id=?",[pid],one=True)
    if not p: flash('Patient introuvable.','error'); return redirect('/patients')
    if request.method == 'POST':
        f=request.form
        ex("UPDATE patients SET nom=?,prenom=?,date_naissance=?,sexe=?,telephone=?,email=?,adresse=?,groupe_sanguin=?,allergie=? WHERE id=?",
           [f['nom'],f['prenom'],f.get('date_naissance') or None,f.get('sexe'),f.get('telephone'),f.get('email'),f.get('adresse'),f.get('groupe_sanguin'),f.get('allergie'),pid])
        flash('Dossier patient mis à jour.','success'); return redirect(f'/patients/{pid}')
    grp_opts=''.join(f'<option {"selected" if p["groupe_sanguin"]==g else ""} value="{g}">{g}</option>' for g in ['A+','A-','B+','B-','AB+','AB-','O+','O-'])
    content=f'''
<div class="mb-3"><a href="/patients/{pid}" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:740px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-pencil-square"></i> Modifier Patient · {p["num_dossier"]}</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="row">
      <div class="col-6 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" value="{p["nom"]}" required></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Prénom *</label><input type="text" name="prenom" class="lt-form-control" value="{p["prenom"]}" required></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Date naissance</label><input type="date" name="date_naissance" class="lt-form-control" value="{p["date_naissance"] or ""}"></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Sexe</label><select name="sexe" class="lt-form-control"><option value="">—</option><option {"selected" if p["sexe"]=="M" else ""} value="M">Masculin</option><option {"selected" if p["sexe"]=="F" else ""} value="F">Féminin</option></select></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Groupe sanguin</label><select name="groupe_sanguin" class="lt-form-control"><option value="">—</option>{grp_opts}</select></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Téléphone</label><input type="tel" name="telephone" class="lt-form-control" value="{p["telephone"] or ""}"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Email</label><input type="email" name="email" class="lt-form-control" value="{p["email"] or ""}"></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Adresse</label><input type="text" name="adresse" class="lt-form-control" value="{p["adresse"] or ""}"></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Allergies</label><textarea name="allergie" class="lt-form-control">{p["allergie"] or ""}</textarea></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Mettre à jour</button><a href="/patients/{pid}" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Modifier Patient', content, 'patients')

@app.route('/patients/<int:pid>/delete', methods=['POST'])
@login_required
@roles_allowed('admin','accueil')
def patient_delete(pid):
    ex("DELETE FROM patients WHERE id=?",[pid]); flash('Patient supprimé.','success'); return redirect('/patients')

# ================================================================
# MÉDECINS & SERVICES
# ================================================================
@app.route('/medecins')
@login_required
@roles_allowed('admin')
def medecins():
    docs = q("SELECT m.*,s.nom svc FROM medecins m LEFT JOIN services s ON m.service_id=s.id ORDER BY m.nom")
    svcs = q("SELECT * FROM services ORDER BY nom")
    svc_opts=''.join(f'<option value="{s["id"]}">{s["nom"]}</option>' for s in svcs)
    doc_rows=''.join(f'''<tr>
        <td><div style="display:flex;align-items:center;gap:10px">
          <div style="width:38px;height:38px;border-radius:10px;background:var(--grn-700);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px">{d["nom"][0].upper()}</div>
          <div><div class="fw-600">Dr. {d["nom"]} {d["prenom"]}</div><small class="text-muted">{d["specialite"] or "—"}</small></div>
        </div></td>
        <td>{d["svc"] or "—"}</td>
        <td>{d["telephone"] or "—"}</td>
        <td>{"<span class='lt-badge lt-badge-confirme'><i class='bi bi-camera-video me-1'></i>Oui</span>" if d["teleconsultation_active"] else "<span class='lt-badge lt-badge-effectue'>Non</span>"}</td>
        <td style="display:flex;gap:4px">
          <a href="/medecins/{d["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a>
          <form method="POST" action="/medecins/{d["id"]}/delete" style="display:inline" onsubmit="return confirm('Supprimer ?')"><button class="lt-btn lt-btn-xs" style="background:var(--red-50);color:var(--red-700);border:1px solid var(--red-100)"><i class="bi bi-trash"></i></button></form>
        </td>
    </tr>''' for d in docs)
    svc_rows=''.join(f'<tr><td><b>{s["nom"]}</b></td><td>{s["description"] or "—"}</td><td><a href="/services/{s["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a></td></tr>' for s in svcs) or '<tr><td colspan="3" style="text-align:center;padding:16px;color:var(--text-muted)">Aucun service</td></tr>'
    content=f'''
<div class="page-title"><i class="bi bi-person-badge-fill"></i> Médecins &amp; Services</div>
<div style="display:grid;grid-template-columns:1fr 320px;gap:20px">
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-person-badge-fill"></i> Médecins ({len(docs)})</span>
      <button class="lt-btn lt-btn-primary lt-btn-sm" onclick="document.getElementById('mMed').style.display='flex'"><i class="bi bi-person-plus-fill"></i> Ajouter</button></div>
    <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Médecin</th><th>Service</th><th>Téléphone</th><th>Téléconsult.</th><th>Actions</th></tr></thead><tbody>{doc_rows}</tbody></table></div>
  </div>
  <div class="lt-card">
    <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-hospital"></i> Services ({len(svcs)})</span>
      <button class="lt-btn lt-btn-outline lt-btn-sm" onclick="document.getElementById('mSvc').style.display='flex'"><i class="bi bi-plus"></i> Ajouter</button></div>
    <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Service</th><th>Description</th><th></th></tr></thead><tbody>{svc_rows}</tbody></table></div>
  </div>
</div>
<div id="mMed" style="display:none;position:fixed;inset:0;background:rgba(2,26,13,.55);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:16px;width:100%;max-width:520px;max-height:90vh;overflow-y:auto;box-shadow:var(--shadow-lg)">
    <div style="padding:18px 24px;border-bottom:1px solid var(--border-light);display:flex;align-items:center;justify-content:space-between">
      <span class="font-display" style="font-size:16px;font-weight:600;color:var(--grn-800)"><i class="bi bi-person-plus-fill me-2"></i>Nouveau Médecin</span>
      <button onclick="document.getElementById('mMed').style.display='none'" style="background:none;border:none;font-size:22px;cursor:pointer;color:#888">&times;</button>
    </div>
    <form method="POST" action="/medecins/new" style="padding:22px">
      <div class="row">
        <div class="col-6 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" required></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Prénom *</label><input type="text" name="prenom" class="lt-form-control" required></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Spécialité</label><input type="text" name="specialite" class="lt-form-control"></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Service</label><select name="service_id" class="lt-form-control"><option value="">— Aucun —</option>{svc_opts}</select></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Téléphone</label><input type="tel" name="telephone" class="lt-form-control"></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Email</label><input type="email" name="email" class="lt-form-control"></div>
        <div class="col-12 mb-3"><label style="display:flex;align-items:center;gap:8px;cursor:pointer"><input type="checkbox" name="teleconsultation_active" value="1"> Téléconsultation activée</label></div>
      </div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Enregistrer</button>
        <button type="button" onclick="document.getElementById('mMed').style.display='none'" class="lt-btn lt-btn-outline">Annuler</button></div>
    </form>
  </div>
</div>
<div id="mSvc" style="display:none;position:fixed;inset:0;background:rgba(2,26,13,.55);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:16px;width:100%;max-width:420px;box-shadow:var(--shadow-lg)">
    <div style="padding:18px 24px;border-bottom:1px solid var(--border-light);display:flex;align-items:center;justify-content:space-between">
      <span class="font-display" style="font-size:16px;font-weight:600;color:var(--grn-800)"><i class="bi bi-hospital me-2"></i>Nouveau Service</span>
      <button onclick="document.getElementById('mSvc').style.display='none'" style="background:none;border:none;font-size:22px;cursor:pointer;color:#888">&times;</button>
    </div>
    <form method="POST" action="/services/new" style="padding:22px">
      <div class="mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" required></div>
      <div class="mb-3"><label class="lt-form-label">Description</label><textarea name="description" class="lt-form-control"></textarea></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Enregistrer</button>
        <button type="button" onclick="document.getElementById('mSvc').style.display='none'" class="lt-btn lt-btn-outline">Annuler</button></div>
    </form>
  </div>
</div>'''
    return layout('Médecins &amp; Services', content, 'medecins')

@app.route('/medecins/new', methods=['POST'])
@login_required
@roles_allowed('admin')
def medecin_new():
    f=request.form
    ex("INSERT INTO medecins(nom,prenom,specialite,service_id,telephone,email,teleconsultation_active) VALUES(?,?,?,?,?,?,?)",
       [f['nom'],f['prenom'],f.get('specialite'),f.get('service_id') or None,f.get('telephone'),f.get('email'),1 if 'teleconsultation_active' in f else 0])
    flash('Médecin ajouté.','success'); return redirect('/medecins')

@app.route('/medecins/<int:mid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin')
def medecin_edit(mid):
    m=q("SELECT * FROM medecins WHERE id=?",[mid],one=True)
    svcs=q("SELECT * FROM services ORDER BY nom")
    if not m: flash('Médecin introuvable.','error'); return redirect('/medecins')
    if request.method=='POST':
        f=request.form
        ex("UPDATE medecins SET nom=?,prenom=?,specialite=?,service_id=?,telephone=?,email=?,teleconsultation_active=? WHERE id=?",
           [f['nom'],f['prenom'],f.get('specialite'),f.get('service_id') or None,f.get('telephone'),f.get('email'),1 if 'teleconsultation_active' in f else 0,mid])
        flash('Médecin mis à jour.','success'); return redirect('/medecins')
    svc_opts=''.join(f'<option value="{s["id"]}" {"selected" if m["service_id"]==s["id"] else ""}>{s["nom"]}</option>' for s in svcs)
    content=f'''
<div class="mb-3"><a href="/medecins" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:580px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-pencil-square"></i> Modifier Médecin</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="row">
      <div class="col-6 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" value="{m["nom"]}" required></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Prénom *</label><input type="text" name="prenom" class="lt-form-control" value="{m["prenom"]}" required></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Spécialité</label><input type="text" name="specialite" class="lt-form-control" value="{m["specialite"] or ""}"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Service</label><select name="service_id" class="lt-form-control"><option value="">— Aucun —</option>{svc_opts}</select></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Téléphone</label><input type="tel" name="telephone" class="lt-form-control" value="{m["telephone"] or ""}"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Email</label><input type="email" name="email" class="lt-form-control" value="{m["email"] or ""}"></div>
      <div class="col-12 mb-3"><label style="display:flex;align-items:center;gap:8px;cursor:pointer"><input type="checkbox" name="teleconsultation_active" value="1" {"checked" if m["teleconsultation_active"] else ""}> Téléconsultation activée</label></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Mettre à jour</button><a href="/medecins" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Modifier Médecin', content, 'medecins')

@app.route('/medecins/<int:mid>/delete', methods=['POST'])
@login_required
@roles_allowed('admin')
def medecin_delete(mid):
    ex("DELETE FROM medecins WHERE id=?",[mid]); flash('Médecin supprimé.','success'); return redirect('/medecins')

@app.route('/services/new', methods=['POST'])
@login_required
@roles_allowed('admin')
def service_new():
    f=request.form; ex("INSERT INTO services(nom,description) VALUES(?,?)",[f['nom'],f.get('description')]); flash('Service ajouté.','success'); return redirect('/medecins')

@app.route('/services/<int:sid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin')
def service_edit(sid):
    s=q("SELECT * FROM services WHERE id=?",[sid],one=True)
    if not s: flash('Service introuvable.','error'); return redirect('/medecins')
    if request.method=='POST':
        f=request.form; ex("UPDATE services SET nom=?,description=? WHERE id=?",[f['nom'],f.get('description'),sid]); flash('Service mis à jour.','success'); return redirect('/medecins')
    content=f'''
<div class="mb-3"><a href="/medecins" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:460px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-hospital"></i> Modifier Service</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" value="{s["nom"]}" required></div>
    <div class="mb-3"><label class="lt-form-label">Description</label><textarea name="description" class="lt-form-control">{s["description"] or ""}</textarea></div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Mettre à jour</button><a href="/medecins" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Modifier Service', content, 'medecins')

# ================================================================
# RENDEZ-VOUS
# ================================================================
@app.route('/rendez-vous')
@login_required
@roles_allowed('admin','accueil','medecin')
def rendez_vous():
    role=session.get('user_role'); mid=session.get('medecin_id')
    fs=request.args.get('statut',''); fd=request.args.get('date',''); fm=request.args.get('medecin_id','')
    cond,params=[],[]
    if role=='medecin' and mid: cond.append("r.medecin_id=?"); params.append(mid)
    if fs: cond.append("r.statut=?"); params.append(fs)
    if fd: cond.append("r.date=?"); params.append(fd)
    if fm and role!='medecin': cond.append("r.medecin_id=?"); params.append(fm)
    where=("WHERE "+" AND ".join(cond)) if cond else ""
    rows=q(f"""SELECT r.*,p.nom||' '||p.prenom pat,p.num_dossier nd,m.nom||' '||m.prenom med,s.nom svc
                FROM rendez_vous r JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id
                LEFT JOIN services s ON m.service_id=s.id {where} ORDER BY r.date DESC,r.heure DESC""",params)
    meds=q("SELECT * FROM medecins ORDER BY nom")
    so=''.join(f'<option value="{v}" {"selected" if fs==v else ""}>{l}</option>' for v,l in [('','Tous'),('planifie','Planifié'),('confirme','Confirmé'),('annule','Annulé'),('effectue','Effectué')])
    mo='<option value="">Tous les médecins</option>'+''.join(f'<option value="{m["id"]}" {"selected" if fm==str(m["id"]) else ""}>Dr. {m["nom"]} {m["prenom"]}</option>' for m in meds)
    trs=''
    for r in rows:
        hc=q("SELECT id FROM consultations WHERE rdv_id=?",[r['id']],one=True)
        acts=f'<a href="/rendez-vous/{r["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a>'
        if r['statut'] in ('planifie','confirme') and not hc:
            acts+=f'<a href="/consultations/new?rdv_id={r["id"]}" class="lt-btn lt-btn-success lt-btn-xs"><i class="bi bi-clipboard2-plus"></i></a>'
        if r['statut']=='planifie':
            acts+=f'<form method="POST" action="/rendez-vous/{r["id"]}/statut" style="display:inline"><input type="hidden" name="statut" value="annule"><button class="lt-btn lt-btn-xs" style="background:var(--red-50);color:var(--red-700);border:1px solid var(--red-100)" onclick="return confirm(\'Annuler ?\')"><i class="bi bi-x-circle"></i></button></form>'
        trs+=f'''<tr>
            <td><b>{r["date"]}</b><br><small class="text-muted">{r["heure"]}</small></td>
            <td><div class="fw-600">{r["pat"]}</div><small class="text-muted">{r["nd"]}</small></td>
            <td>Dr. {r["med"]}<br><small class="text-muted">{r["svc"] or "—"}</small></td>
            <td>{badge(r["statut"])}</td>
            <td>{"<span class='lt-badge lt-badge-tele'><i class='bi bi-camera-video me-1'></i>Télé</span>" if r["type"]=="teleconsultation" else "<span class='lt-badge lt-badge-effectue'>Présentiel</span>"}</td>
            <td><small>{r["motif"] or "—"}</small></td>
            <td style="display:flex;gap:4px">{acts}</td>
        </tr>'''
    if not trs: trs='<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-muted)">Aucun rendez-vous</td></tr>'
    content=f'''
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
  <div class="page-title" style="margin:0"><i class="bi bi-calendar-check-fill"></i> Rendez-vous</div>
  <a href="/rendez-vous/new" class="lt-btn lt-btn-primary"><i class="bi bi-calendar-plus-fill"></i> Nouveau RDV</a>
</div>
<div class="lt-card">
  <div class="lt-card-header" style="flex-wrap:wrap;gap:10px">
    <form method="GET" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;flex:1">
      <div><label class="lt-form-label" style="font-size:11px">Statut</label><select name="statut" class="lt-form-control" style="width:150px">{so}</select></div>
      <div><label class="lt-form-label" style="font-size:11px">Date</label><input type="date" name="date" value="{fd}" class="lt-form-control" style="width:160px"></div>
      {f'<div><label class="lt-form-label" style="font-size:11px">Médecin</label><select name="medecin_id" class="lt-form-control" style="width:200px">{mo}</select></div>' if role!='medecin' else ""}
      <button class="lt-btn lt-btn-outline lt-btn-sm" style="align-self:flex-end"><i class="bi bi-funnel"></i> Filtrer</button>
    </form>
    <span class="text-muted" style="font-size:13px;align-self:flex-end">{len(rows)} RDV</span>
  </div>
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date/Heure</th><th>Patient</th><th>Médecin</th><th>Statut</th><th>Type</th><th>Motif</th><th>Actions</th></tr></thead><tbody>{trs}</tbody></table></div>
</div>'''
    return layout('Rendez-vous', content, 'rendez_vous')

@app.route('/rendez-vous/new', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil','medecin')
def rdv_new():
    patients_list=q("SELECT id,nom,prenom,num_dossier FROM patients ORDER BY nom")
    medecins_list=q("SELECT m.*,s.nom svc FROM medecins m LEFT JOIN services s ON m.service_id=s.id ORDER BY m.nom")
    role=session.get('user_role',''); mid=session.get('medecin_id')
    pre_patient=request.args.get('patient_id','')
    if request.method=='POST':
        f=request.form
        conflit=q("SELECT id FROM rendez_vous WHERE medecin_id=? AND date=? AND heure=? AND statut NOT IN ('annule')",[f['medecin_id'],f['date'],f['heure']],one=True)
        if conflit: flash('Créneau déjà occupé pour ce médecin. Choisissez une autre heure.','error')
        else:
            typ=f.get('type','presentiel')
            if typ=='teleconsultation':
                tc=q("SELECT teleconsultation_active FROM medecins WHERE id=?",[f['medecin_id']],one=True)
                if not tc or not tc['teleconsultation_active']:
                    flash('Ce médecin n\'a pas activé la téléconsultation.','error'); return redirect('/rendez-vous/new')
            rid=ex("INSERT INTO rendez_vous(patient_id,medecin_id,date,heure,motif,type,statut) VALUES(?,?,?,?,?,?,?)",
                   [f['patient_id'],f['medecin_id'],f['date'],f['heure'],f.get('motif'),typ,'planifie'])
            if typ=='teleconsultation':
                ex("INSERT INTO teleconsultations(rdv_id,statut) VALUES(?,?)",[rid,'planifiee'])
                m_info=q("SELECT nom,prenom FROM medecins WHERE id=?",[f['medecin_id']],one=True)
                msg = f"Téléconsultation planifiée avec Dr. {m_info['nom']} {m_info['prenom']} le {f['date']} à {f['heure']}. Le lien de connexion vous sera communiqué prochainement."
                add_notification(int(f['patient_id']),'📹 Téléconsultation planifiée',msg)
            else:
                m_info=q("SELECT nom,prenom FROM medecins WHERE id=?",[f['medecin_id']],one=True)
                msg = f"Rendez-vous planifié avec Dr. {m_info['nom']} {m_info['prenom']} le {f['date']} à {f['heure']}. Motif : {f.get('motif') or 'Non précisé'}."
                add_notification(int(f['patient_id']),'📅 Nouveau rendez-vous',msg)
            flash('Rendez-vous créé avec succès.','success')
            return redirect('/rendez-vous')
    pre_med = str(mid) if role=='medecin' and mid else ''
    pat_opts='<option value="">— Sélectionner un patient —</option>'+''.join(f'<option value="{p["id"]}" {"selected" if str(p["id"])==pre_patient else ""}>{p["nom"]} {p["prenom"]} ({p["num_dossier"]})</option>' for p in patients_list)
    med_opts='<option value="">— Sélectionner un médecin —</option>'+''.join(f'<option value="{m["id"]}" {"selected" if str(m["id"])==pre_med else ""}>Dr. {m["nom"]} {m["prenom"]} — {m["svc"] or "Général"}{"  📹" if m["teleconsultation_active"] else ""}</option>' for m in medecins_list)
    content=f'''
<div class="mb-3"><a href="/rendez-vous" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:640px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-calendar-plus-fill"></i> Nouveau Rendez-vous</span></div>
  <div class="lt-card-body">
    <div class="lt-alert lt-alert-info mb-3"><i class="bi bi-info-circle-fill"></i><div>Vérification automatique des conflits. La téléconsultation (📹) nécessite l'activation par le médecin. Le patient recevra une notification.</div></div>
    <form method="POST">
      <div class="mb-3"><label class="lt-form-label">Patient *</label><select name="patient_id" class="lt-form-control" required>{pat_opts}</select></div>
      <div class="mb-3"><label class="lt-form-label">Médecin *</label><select name="medecin_id" class="lt-form-control" required {"disabled" if role=="medecin" else ""}>{med_opts}</select>
        {f'<input type="hidden" name="medecin_id" value="{pre_med}">' if role=="medecin" else ""}</div>
      <div class="row">
        <div class="col-6 mb-3"><label class="lt-form-label">Date *</label><input type="date" name="date" class="lt-form-control" required min="{date.today().isoformat()}"></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Heure *</label><input type="time" name="heure" class="lt-form-control" required></div>
      </div>
      <div class="mb-3"><label class="lt-form-label">Type</label><select name="type" class="lt-form-control"><option value="presentiel">Présentiel</option><option value="teleconsultation">Téléconsultation 📹</option></select></div>
      <div class="mb-3"><label class="lt-form-label">Motif</label><textarea name="motif" class="lt-form-control" placeholder="Motif de la consultation..."></textarea></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Créer le RDV</button><a href="/rendez-vous" class="lt-btn lt-btn-outline">Annuler</a></div>
    </form>
  </div>
</div>'''
    return layout('Nouveau Rendez-vous', content, 'rendez_vous')

@app.route('/rendez-vous/<int:rid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil','medecin')
def rdv_edit(rid):
    r=q("SELECT * FROM rendez_vous WHERE id=?",[rid],one=True)
    if not r: flash('RDV introuvable.','error'); return redirect('/rendez-vous')
    if request.method=='POST':
        f=request.form
        ex("UPDATE rendez_vous SET statut=?,motif=?,date=?,heure=? WHERE id=?",[f.get('statut',r['statut']),f.get('motif'),f.get('date',r['date']),f.get('heure',r['heure']),rid])
        flash('Rendez-vous mis à jour.','success'); return redirect('/rendez-vous')
    p=q("SELECT nom,prenom FROM patients WHERE id=?",[r['patient_id']],one=True)
    m=q("SELECT nom,prenom FROM medecins WHERE id=?",[r['medecin_id']],one=True)
    so=''.join(f'<option value="{v}" {"selected" if r["statut"]==v else ""}>{l}</option>' for v,l in [('planifie','Planifié'),('confirme','Confirmé'),('annule','Annulé'),('effectue','Effectué')])
    content=f'''
<div class="mb-3"><a href="/rendez-vous" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:520px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-pencil-square"></i> Modifier RDV #{rid}</span></div>
  <div class="lt-card-body">
    <div class="lt-alert lt-alert-info mb-3"><i class="bi bi-person-fill"></i><b>{p["prenom"]} {p["nom"]}</b> → Dr. {m["nom"]} {m["prenom"]}</div>
    <form method="POST">
      <div class="row">
        <div class="col-6 mb-3"><label class="lt-form-label">Date</label><input type="date" name="date" class="lt-form-control" value="{r["date"]}"></div>
        <div class="col-6 mb-3"><label class="lt-form-label">Heure</label><input type="time" name="heure" class="lt-form-control" value="{r["heure"]}"></div>
      </div>
      <div class="mb-3"><label class="lt-form-label">Statut</label><select name="statut" class="lt-form-control">{so}</select></div>
      <div class="mb-3"><label class="lt-form-label">Motif</label><textarea name="motif" class="lt-form-control">{r["motif"] or ""}</textarea></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Mettre à jour</button><a href="/rendez-vous" class="lt-btn lt-btn-outline">Annuler</a></div>
    </form>
  </div>
</div>'''
    return layout('Modifier Rendez-vous', content, 'rendez_vous')

@app.route('/rendez-vous/<int:rid>/statut', methods=['POST'])
@login_required
def rdv_statut(rid):
    statut=request.form.get('statut')
    if statut:
        ex("UPDATE rendez_vous SET statut=? WHERE id=?",[statut,rid])
        if statut=='annule':
            rdv=q("SELECT medecin_id,patient_id FROM rendez_vous WHERE id=?",[rid],one=True)
            if rdv:
                att=q("SELECT la.*,p.nom,p.prenom FROM liste_attente la JOIN patients p ON la.patient_id=p.id WHERE la.medecin_id=? ORDER BY la.priorite DESC,la.date_inscription ASC LIMIT 1",[rdv['medecin_id']],one=True)
                if att: flash(f'<b>{att["prenom"]} {att["nom"]}</b> est en liste d\'attente pour ce médecin.','info')
                add_notification(rdv['patient_id'],'❌ Rendez-vous annulé','Votre rendez-vous a été annulé. Veuillez contacter l\'accueil pour replanifier.')
        flash('Statut mis à jour.','success')
    return redirect('/rendez-vous')

# ================================================================
# CONSULTATIONS & ORDONNANCES
# ================================================================
@app.route('/consultations')
@login_required
@roles_allowed('admin','accueil','medecin')
def consultations():
    role=session.get('user_role'); mid=session.get('medecin_id')
    if role=='medecin' and mid:
        rows=q("""SELECT c.*,r.date rd,r.heure rh,p.nom||' '||p.prenom pat,p.num_dossier nd,m.nom||' '||m.prenom med,o.id oid,f.statut fst FROM consultations c JOIN rendez_vous r ON c.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id LEFT JOIN ordonnances o ON o.consultation_id=c.id LEFT JOIN factures f ON f.consultation_id=c.id WHERE r.medecin_id=? ORDER BY c.date DESC""",[mid])
    else:
        rows=q("""SELECT c.*,r.date rd,r.heure rh,p.nom||' '||p.prenom pat,p.num_dossier nd,m.nom||' '||m.prenom med,o.id oid,f.statut fst FROM consultations c JOIN rendez_vous r ON c.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id LEFT JOIN ordonnances o ON o.consultation_id=c.id LEFT JOIN factures f ON f.consultation_id=c.id ORDER BY c.date DESC""")
    trs=''.join(f'''<tr>
        <td><b>{c["rd"]}</b> <small class="text-muted">{c["rh"]}</small></td>
        <td>{c["pat"]}<br><small class="text-muted">{c["nd"]}</small></td>
        <td>Dr. {c["med"]}</td>
        <td><small>{(c["diagnostic"] or "—")[:55]}</small></td>
        <td>{"<span class='lt-badge lt-badge-confirme'><i class='bi bi-prescription2 me-1'></i>Oui</span>" if c["oid"] else "<span class='lt-badge lt-badge-effectue'>Non</span>"}</td>
        <td>{badge(c["fst"]) if c["fst"] else "—"}</td>
        <td><a href="/consultations/{c["id"]}" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-eye"></i></a></td>
    </tr>''' for c in rows) or '<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-muted)">Aucune consultation</td></tr>'
    content=f'''
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
  <div class="page-title" style="margin:0"><i class="bi bi-clipboard2-pulse-fill"></i> Consultations</div>
  <a href="/consultations/new" class="lt-btn lt-btn-primary"><i class="bi bi-clipboard2-plus-fill"></i> Nouvelle consultation</a>
</div>
<div class="lt-card">
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date</th><th>Patient</th><th>Médecin</th><th>Diagnostic</th><th>Ordonnance</th><th>Facture</th><th>Action</th></tr></thead><tbody>{trs}</tbody></table></div>
  <div class="lt-card-footer">{len(rows)} consultation(s)</div>
</div>'''
    return layout('Consultations', content, 'consultations')

@app.route('/consultations/new', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil','medecin')
def consultation_new():
    role=session.get('user_role'); mid=session.get('medecin_id')
    pre_rdv=request.args.get('rdv_id','')
    if role=='medecin' and mid:
        rdvs=q("""SELECT r.id,r.date,r.heure,p.nom||' '||p.prenom pat,m.nom||' '||m.prenom med FROM rendez_vous r JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id WHERE r.medecin_id=? AND r.statut IN ('planifie','confirme') AND r.id NOT IN (SELECT rdv_id FROM consultations) ORDER BY r.date DESC""",[mid])
    else:
        rdvs=q("""SELECT r.id,r.date,r.heure,p.nom||' '||p.prenom pat,m.nom||' '||m.prenom med FROM rendez_vous r JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id WHERE r.statut IN ('planifie','confirme') AND r.id NOT IN (SELECT rdv_id FROM consultations) ORDER BY r.date DESC""")
    if request.method=='POST':
        f=request.form; montant=float(f.get('montant') or 5000)
        cid=ex("INSERT INTO consultations(rdv_id,diagnostic,notes) VALUES(?,?,?)",[int(f['rdv_id']),f.get('diagnostic'),f.get('notes')])
        ex("UPDATE rendez_vous SET statut='effectue' WHERE id=?",[f['rdv_id']])
        ex("INSERT INTO factures(consultation_id,montant_total,montant_patient,statut,date) VALUES(?,?,?,?,?)",[cid,montant,montant,'impayee',date.today().isoformat()])
        rdv_info=q("SELECT patient_id FROM rendez_vous WHERE id=?",[int(f['rdv_id'])],one=True)
        if rdv_info:
            add_notification(rdv_info['patient_id'],'📋 Consultation effectuée',f'Votre consultation a été enregistrée. Une facture de {fcfa(montant)} a été générée. Rendez-vous à l\'accueil pour le règlement.')
        flash('Consultation enregistrée. Facture créée automatiquement.','success')
        return redirect(f'/consultations/{cid}')
    rdv_opts='<option value="">— Sélectionner un rendez-vous validé —</option>'+''.join(f'<option value="{r["id"]}" {"selected" if str(r["id"])==pre_rdv else ""}>[{r["date"]} {r["heure"]}] {r["pat"]} → Dr. {r["med"]}</option>' for r in rdvs)
    content=f'''
<div class="mb-3"><a href="/consultations" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:680px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-clipboard2-plus-fill"></i> Nouvelle Consultation</span></div>
  <div class="lt-card-body">
    <div class="lt-alert lt-alert-info mb-3"><i class="bi bi-info-circle-fill"></i><div>Consultation depuis un RDV validé uniquement. Une facture est créée automatiquement et le patient est notifié.</div></div>
    <form method="POST">
      <div class="mb-3"><label class="lt-form-label">Rendez-vous *</label><select name="rdv_id" class="lt-form-control" required>{rdv_opts}</select></div>
      <div class="mb-3"><label class="lt-form-label">Diagnostic</label><textarea name="diagnostic" class="lt-form-control" placeholder="Saisir le diagnostic clinique..."></textarea></div>
      <div class="mb-3"><label class="lt-form-label">Notes cliniques</label><textarea name="notes" class="lt-form-control" placeholder="Observations, examens complémentaires..."></textarea></div>
      <div class="mb-3"><label class="lt-form-label">Montant consultation (FCFA)</label><input type="number" name="montant" class="lt-form-control" value="5000" min="0" step="100"></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Enregistrer</button><a href="/consultations" class="lt-btn lt-btn-outline">Annuler</a></div>
    </form>
  </div>
</div>'''
    return layout('Nouvelle Consultation', content, 'consultations')

@app.route('/consultations/<int:cid>')
@login_required
@roles_allowed('admin','accueil','medecin','pharmacien')
def consultation_view(cid):
    c=q("""SELECT c.*,r.date rd,r.heure rh,r.motif mot,p.nom||' '||p.prenom pat,p.num_dossier nd,p.id pid,m.nom||' '||m.prenom med,m.specialite FROM consultations c JOIN rendez_vous r ON c.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id WHERE c.id=?""",[cid],one=True)
    if not c: flash('Consultation introuvable.','error'); return redirect('/consultations')
    ordo=q("SELECT * FROM ordonnances WHERE consultation_id=?",[cid],one=True)
    fact=q("SELECT * FROM factures WHERE consultation_id=?",[cid],one=True)
    lignes=q("SELECT lo.*,med.nom mn FROM lignes_ordonnance lo JOIN medicaments med ON lo.medicament_id=med.id WHERE lo.ordonnance_id=?",[ordo['id']]) if ordo else []
    meds=q("SELECT id,nom,stock FROM medicaments WHERE stock>0 ORDER BY nom")
    med_opts=''.join(f'<option value="{m["id"]}">{m["nom"]} (stock: {m["stock"]})</option>' for m in meds)
    lignes_html=''.join(f'<tr><td><b>{l["mn"]}</b></td><td>{l["dosage"] or "—"}</td><td>{l["frequence"] or "—"}</td><td>{l["duree"] or "—"}</td><td class="text-center">{l["quantite"]}</td></tr>' for l in lignes) or '<tr><td colspan="5" style="text-align:center;padding:14px;color:var(--text-muted)">Aucun médicament prescrit</td></tr>'
    role=session.get('user_role')
    can_edit=(role in ('admin','medecin'))
    if ordo:
        ordo_sec=f'''
<div class="lt-card">
  <div class="lt-card-header">
    <span class="lt-card-title"><i class="bi bi-prescription2" style="color:var(--grn-600)"></i> Ordonnance N°{ordo["id"]} — {ordo["date"]}</span>
    <button class="lt-btn lt-btn-outline lt-btn-sm no-print" onclick="window.print()"><i class="bi bi-printer"></i> Imprimer</button>
  </div>
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Médicament</th><th>Dosage</th><th>Fréquence</th><th>Durée</th><th style="text-align:center">Qté</th></tr></thead><tbody>{lignes_html}</tbody></table></div>
  <div class="lt-card-footer">Prescrit par Dr. {c["med"]} · {c["specialite"] or "Généraliste"}</div>
</div>
{f"""<div class="lt-card no-print">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-plus-circle"></i> Ajouter un médicament à l'ordonnance</span></div>
  <div class="lt-card-body"><form method="POST" action="/ordonnances/{ordo["id"]}/ligne">
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
      <div><label class="lt-form-label">Médicament *</label><select name="medicament_id" class="lt-form-control" style="width:220px" required><option value="">— Choisir —</option>{med_opts}</select></div>
      <div><label class="lt-form-label">Dosage</label><input type="text" name="dosage" class="lt-form-control" style="width:100px" placeholder="1 cp"></div>
      <div><label class="lt-form-label">Fréquence</label><input type="text" name="frequence" class="lt-form-control" style="width:100px" placeholder="3×/j"></div>
      <div><label class="lt-form-label">Durée</label><input type="text" name="duree" class="lt-form-control" style="width:100px" placeholder="7 jours"></div>
      <div><label class="lt-form-label">Qté</label><input type="number" name="quantite" class="lt-form-control" style="width:70px" value="1" min="1"></div>
      <button type="submit" class="lt-btn lt-btn-success" style="align-self:flex-end"><i class="bi bi-plus"></i> Ajouter</button>
    </div>
    <small class="text-muted" style="display:block;margin-top:8px">Le stock diminuera automatiquement à la prescription.</small>
  </form></div>
</div>""" if can_edit else ""}'''
    else:
        ordo_sec=f'''
<div class="lt-card">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-prescription2"></i> Ordonnance</span></div>
  <div class="lt-card-body" style="text-align:center;padding:30px">
    <p class="text-muted mb-3">Aucune ordonnance pour cette consultation.</p>
    {f"""<form method="POST" action="/ordonnances/new"><input type="hidden" name="consultation_id" value="{cid}"><button type="submit" class="lt-btn lt-btn-success"><i class="bi bi-prescription2"></i> Créer une ordonnance</button></form><small class="text-muted" style="display:block;margin-top:8px">Une consultation peut générer 0 ou 1 ordonnance.</small>""" if can_edit else '<small class="text-muted">Aucune ordonnance créée.</small>'}
  </div>
</div>'''
    fact_sec=''
    if fact:
        fact_sec=f'''
<div class="lt-card">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-receipt-cutoff"></i> Facture N°{fact["id"]}</span>{badge(fact["statut"])}</div>
  <div class="lt-card-body">
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:center">
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase">Total</div><div class="font-display" style="font-size:20px;font-weight:700">{fcfa(fact["montant_total"])}</div></div>
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase">Assurance</div><div class="font-display text-success" style="font-size:20px;font-weight:700">{fcfa(fact["montant_assurance"])}</div></div>
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase">À payer</div><div class="font-display text-danger" style="font-size:20px;font-weight:700">{fcfa(fact["montant_patient"])}</div></div>
    </div>
    {f'<div style="text-align:center;margin-top:14px"><a href="/facturation/{cid}" class="lt-btn lt-btn-outline lt-btn-sm">Gérer la facture</a></div>' if fact["statut"]!="payee" and role in ("admin","accueil") else ""}
  </div>
</div>'''
    content=f'''
<div style="display:flex;justify-content:space-between;margin-bottom:18px" class="no-print">
  <a href="/consultations" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a>
  <a href="/patients/{c["pid"]}" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-person"></i> Dossier patient</a>
</div>
<div class="lt-card">
  <div class="lt-card-header" style="background:var(--grn-800)">
    <span class="lt-card-title" style="color:#fff"><i class="bi bi-clipboard2-pulse-fill me-2"></i>Consultation N°{cid} — {c["rd"]}</span>
    <button class="lt-btn lt-btn-sm no-print" style="background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.2)" onclick="window.print()"><i class="bi bi-printer"></i></button>
  </div>
  <div class="lt-card-body">
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:18px">
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:4px">Patient</div><div class="fw-600">{c["pat"]}</div><small class="text-muted">{c["nd"]}</small></div>
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:4px">Médecin</div><div class="fw-600">Dr. {c["med"]}</div><small class="text-muted">{c["specialite"] or "Généraliste"}</small></div>
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:4px">Date / Heure</div><div class="fw-600">{c["rd"]}</div><small class="text-muted">{c["rh"]}</small></div>
    </div>
    <div class="divider"></div>
    <div class="mb-3"><div class="text-muted mb-1" style="font-size:11px;font-weight:700;text-transform:uppercase">Motif</div><div>{c["mot"] or "—"}</div></div>
    <div class="mb-3"><div class="text-muted mb-1" style="font-size:11px;font-weight:700;text-transform:uppercase">Diagnostic</div><div style="background:var(--surface);border-radius:8px;padding:12px">{c["diagnostic"] or "<em style='color:var(--text-muted)'>Non renseigné</em>"}</div></div>
    <div><div class="text-muted mb-1" style="font-size:11px;font-weight:700;text-transform:uppercase">Notes cliniques</div><div style="background:var(--surface);border-radius:8px;padding:12px">{c["notes"] or "<em style='color:var(--text-muted)'>Aucune note</em>"}</div></div>
  </div>
</div>
{ordo_sec}
{fact_sec}'''
    return layout(f'Consultation N°{cid}', content, 'consultations')

@app.route('/ordonnances/new', methods=['POST'])
@login_required
@roles_allowed('admin','medecin')
def ordonnance_new():
    cid=request.form['consultation_id']
    if q("SELECT id FROM ordonnances WHERE consultation_id=?",[cid],one=True): flash('Ordonnance déjà créée.','error')
    else: ex("INSERT INTO ordonnances(consultation_id,date) VALUES(?,?)",[cid,date.today().isoformat()]); flash('Ordonnance créée.','success')
    return redirect(f'/consultations/{cid}')

# ================================================================
# CORRECTION BUG : suppression de 'ordonnance_id' inexistant
# La table ordonnances a les colonnes : id, consultation_id, date
# ================================================================
@app.route('/ordonnances/<int:oid>/ligne', methods=['POST'])
@login_required
@roles_allowed('admin','medecin')
def ordonnance_ligne(oid):
    f = request.form
    # CORRECTION : on sélectionne uniquement 'consultation_id' qui existe dans la table
    ordo = q("SELECT consultation_id FROM ordonnances WHERE id=?", [oid], one=True)
    if not ordo:
        flash('Ordonnance introuvable.', 'error')
        return redirect('/consultations')
    qte = int(f.get('quantite', 1))
    ex("INSERT INTO lignes_ordonnance(ordonnance_id,medicament_id,dosage,frequence,duree,quantite) VALUES(?,?,?,?,?,?)",
       [oid, f['medicament_id'], f.get('dosage'), f.get('frequence'), f.get('duree'), qte])
    # Décrémenter le stock
    ex("UPDATE medicaments SET stock=MAX(0,stock-?) WHERE id=?", [qte, f['medicament_id']])
    med_info = q("SELECT nom FROM medicaments WHERE id=?", [f['medicament_id']], one=True)
    flash(f'Médicament {med_info["nom"] if med_info else ""} ajouté à l\'ordonnance. Stock mis à jour.', 'success')
    # Notification patient
    c_info = q("""SELECT r.patient_id FROM consultations c
                  JOIN rendez_vous r ON c.rdv_id=r.id
                  WHERE c.id=?""", [ordo['consultation_id']], one=True)
    if c_info:
        add_notification(c_info['patient_id'], '💊 Médicament prescrit',
                         f'{med_info["nom"] if med_info else "Un médicament"} a été prescrit. Rendez-vous à la pharmacie avec votre ordonnance.')
    return redirect(f'/consultations/{ordo["consultation_id"]}')

# ================================================================
# PHARMACIE
# ================================================================
@app.route('/pharmacie')
@login_required
@roles_allowed('admin','pharmacien','medecin')
def pharmacie():
    rows=q("SELECT * FROM medicaments ORDER BY nom")
    nb_alert=sum(1 for m in rows if m['stock']<=m['stock_minimum'])
    role=session.get('user_role','')
    trs=''.join(f'''<tr style="background:{'var(--red-50)' if m['stock']<=m['stock_minimum'] else ''}">
        <td>
          <div class="fw-600">{m["nom"]}</div>
          <small class="text-muted">{(m["description"] or "")[:70]}</small>
        </td>
        <td class="{'stock-lo' if m['stock']<=m['stock_minimum'] else 'stock-ok'}">
          <i class="bi bi-{'exclamation-triangle-fill' if m['stock']<=m['stock_minimum'] else 'check-circle-fill'} me-1"></i>{m["stock"]}
        </td>
        <td class="text-muted">{m["stock_minimum"]}</td>
        <td>{fcfa(m["prix_unitaire"])}</td>
        <td>{m["date_expiration"] or "—"}</td>
        <td>{m["lot"] or "—"}</td>
        <td style="display:flex;gap:4px">
          {f'<a href="/pharmacie/{m["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a>' if role in ("admin","pharmacien") else ""}
          {f'<button class="lt-btn lt-btn-success lt-btn-xs" onclick="openRestock({m["id"]},\'{m["nom"].replace(chr(39),chr(96))}\')"><i class="bi bi-plus-circle"></i></button>' if role in ("admin","pharmacien") else ""}
        </td>
    </tr>''' for m in rows) or '<tr><td colspan="7" style="text-align:center;padding:22px;color:var(--text-muted)">Aucun médicament</td></tr>'
    content=f'''
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
  <div class="page-title" style="margin:0"><i class="bi bi-bag-heart-fill"></i> Pharmacie &amp; Stocks</div>
  {f'<a href="/pharmacie/new" class="lt-btn lt-btn-primary"><i class="bi bi-plus-circle"></i> Nouveau médicament</a>' if role in ("admin","pharmacien") else ""}
</div>
{f"<div class='lt-alert lt-alert-danger mb-3'><i class='bi bi-exclamation-triangle-fill'></i><div><b>{nb_alert} médicament(s) en stock insuffisant !</b> Réapprovisionnement requis.</div></div>" if nb_alert else ""}
<div class="lt-card">
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Médicament</th><th>Stock actuel</th><th>Stock min.</th><th>Prix unitaire</th><th>Expiration</th><th>Lot</th><th>Actions</th></tr></thead><tbody>{trs}</tbody></table></div>
  <div class="lt-card-footer">{len(rows)} médicament(s) · Stock diminue automatiquement à chaque prescription</div>
</div>
<div id="mRestock" style="display:none;position:fixed;inset:0;background:rgba(2,26,13,.55);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:16px;width:100%;max-width:440px;box-shadow:var(--shadow-lg)">
    <div style="padding:18px 24px;border-bottom:1px solid var(--border-light);display:flex;align-items:center;justify-content:space-between">
      <span class="font-display" style="font-size:16px;font-weight:600;color:var(--grn-600)"><i class="bi bi-plus-circle me-2"></i>Réapprovisionnement</span>
      <button onclick="document.getElementById('mRestock').style.display='none'" style="background:none;border:none;font-size:22px;cursor:pointer;color:#888">&times;</button>
    </div>
    <form method="POST" action="/pharmacie/restock" style="padding:22px">
      <p class="mb-3">Médicament : <b id="rst_nom"></b></p>
      <input type="hidden" name="medicament_id" id="rst_id">
      <div class="mb-3"><label class="lt-form-label">Quantité à ajouter *</label><input type="number" name="quantite" class="lt-form-control" min="1" required placeholder="ex : 50"></div>
      <div class="mb-3"><label class="lt-form-label">Nouveau numéro de lot</label><input type="text" name="lot" class="lt-form-control" placeholder="LOT-XXX"></div>
      <div class="mb-3"><label class="lt-form-label">Nouvelle date d'expiration</label><input type="date" name="date_expiration" class="lt-form-control"></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-success"><i class="bi bi-check2"></i> Valider</button>
        <button type="button" onclick="document.getElementById('mRestock').style.display='none'" class="lt-btn lt-btn-outline">Annuler</button></div>
    </form>
  </div>
</div>
<script>function openRestock(id,nom){{document.getElementById('rst_id').value=id;document.getElementById('rst_nom').textContent=nom;document.getElementById('mRestock').style.display='flex';}}</script>'''
    return layout('Pharmacie &amp; Stocks', content, 'pharmacie')

@app.route('/pharmacie/new', methods=['GET','POST'])
@login_required
@roles_allowed('admin','pharmacien')
def pharmacie_new():
    exp_defaut = (date.today() + timedelta(days=365)).isoformat()
    if request.method=='POST':
        f=request.form
        exp = f.get('date_expiration') or exp_defaut
        ex("INSERT INTO medicaments(nom,description,stock,stock_minimum,prix_unitaire,date_expiration,lot) VALUES(?,?,?,?,?,?,?)",
           [f['nom'],f.get('description'),int(f.get('stock',0)),int(f.get('stock_minimum',10)),float(f.get('prix_unitaire',0)),exp,f.get('lot')])
        flash('Médicament ajouté.','success'); return redirect('/pharmacie')
    content=f'''
<div class="mb-3"><a href="/pharmacie" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:620px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-plus-circle"></i> Nouveau Médicament</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="row">
      <div class="col-12 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" required placeholder="ex : Paracétamol 500mg"></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Description *</label><textarea name="description" class="lt-form-control" placeholder="Indication thérapeutique, famille pharmacologique..." required></textarea></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Stock initial</label><input type="number" name="stock" class="lt-form-control" value="0" min="0"></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Stock minimum</label><input type="number" name="stock_minimum" class="lt-form-control" value="10" min="0"></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Prix unitaire (FCFA)</label><input type="number" name="prix_unitaire" class="lt-form-control" value="0" min="0" step="50"></div>
      <div class="col-6 mb-3">
        <label class="lt-form-label">Date d'expiration <small class="text-muted">(défaut : 1 an)</small></label>
        <input type="date" name="date_expiration" class="lt-form-control" value="{exp_defaut}">
      </div>
      <div class="col-6 mb-3"><label class="lt-form-label">N° de lot</label><input type="text" name="lot" class="lt-form-control" placeholder="LOT-XXX"></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Enregistrer</button><a href="/pharmacie" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Nouveau Médicament', content, 'pharmacie')

@app.route('/pharmacie/<int:mid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin','pharmacien')
def pharmacie_edit(mid):
    m=q("SELECT * FROM medicaments WHERE id=?",[mid],one=True)
    if not m: flash('Médicament introuvable.','error'); return redirect('/pharmacie')
    if request.method=='POST':
        f=request.form
        ex("UPDATE medicaments SET nom=?,description=?,stock=?,stock_minimum=?,prix_unitaire=?,date_expiration=?,lot=? WHERE id=?",
           [f['nom'],f.get('description'),int(f.get('stock',0)),int(f.get('stock_minimum',10)),float(f.get('prix_unitaire',0)),f.get('date_expiration') or None,f.get('lot'),mid])
        flash('Médicament mis à jour.','success'); return redirect('/pharmacie')
    content=f'''
<div class="mb-3"><a href="/pharmacie" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:620px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-pencil-square"></i> Modifier Médicament</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="row">
      <div class="col-12 mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" value="{m["nom"]}" required></div>
      <div class="col-12 mb-3"><label class="lt-form-label">Description</label><textarea name="description" class="lt-form-control">{m["description"] or ""}</textarea></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Stock</label><input type="number" name="stock" class="lt-form-control" value="{m["stock"]}"></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Stock minimum</label><input type="number" name="stock_minimum" class="lt-form-control" value="{m["stock_minimum"]}"></div>
      <div class="col-md-4 mb-3"><label class="lt-form-label">Prix unitaire (FCFA)</label><input type="number" name="prix_unitaire" class="lt-form-control" value="{m["prix_unitaire"]}" step="50"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Date d'expiration</label><input type="date" name="date_expiration" class="lt-form-control" value="{m["date_expiration"] or ""}"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">N° de lot</label><input type="text" name="lot" class="lt-form-control" value="{m["lot"] or ""}"></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Mettre à jour</button><a href="/pharmacie" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Modifier Médicament', content, 'pharmacie')

@app.route('/pharmacie/restock', methods=['POST'])
@login_required
@roles_allowed('admin','pharmacien')
def pharmacie_restock():
    f=request.form; mid=f['medicament_id']; qte=int(f.get('quantite',0)); lot=f.get('lot'); exp=f.get('date_expiration') or None
    if lot: ex("UPDATE medicaments SET stock=stock+?,lot=?,date_expiration=? WHERE id=?",[qte,lot,exp,mid])
    else: ex("UPDATE medicaments SET stock=stock+? WHERE id=?",[qte,mid])
    flash(f'Réapprovisionnement : +{qte} unité(s).','success'); return redirect('/pharmacie')

# ================================================================
# FACTURATION
# ================================================================
@app.route('/facturation')
@login_required
@roles_allowed('admin','accueil')
def facturation():
    rows=q("""SELECT f.*,p.nom||' '||p.prenom pat,p.num_dossier nd,p.id pid,r.date rd
              FROM factures f JOIN consultations c ON f.consultation_id=c.id
              JOIN rendez_vous r ON c.rdv_id=r.id JOIN patients p ON r.patient_id=p.id
              ORDER BY f.date DESC""")
    ti=sum(r['montant_patient'] for r in rows if r['statut']=='impayee')
    tp=sum(r['montant_total']   for r in rows if r['statut']=='payee')
    trs=''.join(f'''<tr>
        <td><span class="lt-badge lt-badge-planifie">N°{f["id"]}</span></td>
        <td><div class="fw-600">{f["pat"]}</div><small class="text-muted">{f["nd"]}</small></td>
        <td>{f["rd"]}</td>
        <td class="fw-600">{fcfa(f["montant_total"])}</td>
        <td class="text-success">{fcfa(f["montant_assurance"])}</td>
        <td class="fw-600 {'text-danger' if f['statut']=='impayee' else ''}">{fcfa(f["montant_patient"])}</td>
        <td>{badge(f["statut"])}</td>
        <td style="display:flex;gap:4px">
          <a href="/facturation/{f["consultation_id"]}" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-eye"></i></a>
          {f'<a href="/facturation/{f["consultation_id"]}/payer" class="lt-btn lt-btn-success lt-btn-xs"><i class="bi bi-cash me-1"></i>Payer</a>' if f["statut"]=="impayee" else ""}
        </td>
    </tr>''' for f in rows) or '<tr><td colspan="8" style="text-align:center;padding:22px;color:var(--text-muted)">Aucune facture</td></tr>'
    content=f'''
<div class="page-title"><i class="bi bi-receipt-cutoff"></i> Facturation</div>
<div class="stat-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:22px">
  <div class="stat-card" style="--accent:var(--red-700)"><div class="stat-num" style="font-size:22px">{fcfa(ti)}</div><div class="stat-lbl">Montant impayé</div><i class="bi bi-receipt-cutoff stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--grn-500)"><div class="stat-num" style="font-size:22px">{fcfa(tp)}</div><div class="stat-lbl">Total encaissé</div><i class="bi bi-check-circle-fill stat-icon"></i></div>
  <div class="stat-card" style="--accent:var(--blu-500)"><div class="stat-num">{len(rows)}</div><div class="stat-lbl">Total factures</div><i class="bi bi-files stat-icon"></i></div>
</div>
<div class="lt-card">
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>N° Facture</th><th>Patient</th><th>Date</th><th>Total</th><th>Assurance</th><th>À payer</th><th>Statut</th><th>Actions</th></tr></thead><tbody>{trs}</tbody></table></div>
</div>'''
    return layout('Facturation', content, 'facturation')

@app.route('/facturation/<int:cid>')
@login_required
@roles_allowed('admin','accueil')
def facture_view(cid):
    c=q("""SELECT c.*,f.id fid,f.montant_total mt,f.montant_assurance ma,f.montant_patient mp,f.statut fst,f.date fd,p.nom||' '||p.prenom pat,p.num_dossier nd,p.id pid,p.email pemail,m.nom||' '||m.prenom med,m.specialite spc,r.date rd,r.heure rh FROM consultations c JOIN factures f ON f.consultation_id=c.id JOIN rendez_vous r ON c.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id WHERE c.id=?""",[cid],one=True)
    if not c: flash('Facture introuvable.','error'); return redirect('/facturation')
    ass=q("SELECT pa.*,a.nom an FROM patient_assurance pa JOIN assurances a ON pa.assurance_id=a.id WHERE pa.patient_id=? LIMIT 1",[c['pid']],one=True)
    role=session.get('user_role')
    payer_form=''
    if c['fst']=='impayee':
        payer_form=f'''
<div class="divider"></div>
<div class="font-display" style="font-size:15px;font-weight:600;color:var(--grn-800);margin-bottom:14px">Régler la facture</div>
<form method="POST" action="/facturation/{cid}/payer">
  <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
    <div><label class="lt-form-label">Montant reçu du patient (FCFA)</label><input type="number" name="montant_recu" class="lt-form-control" style="width:200px" value="{int(c['mp'])}" min="0" step="100"></div>
    <div><label class="lt-form-label">Prise en charge assurance (FCFA)</label><input type="number" name="montant_assurance" class="lt-form-control" style="width:200px" value="{int(c['ma'])}" min="0" step="100"></div>
    <button type="submit" class="lt-btn lt-btn-success" style="align-self:flex-end"><i class="bi bi-cash"></i> Valider le paiement</button>
  </div>
  <small class="text-muted" style="display:block;margin-top:8px">Le patient sera notifié automatiquement après le paiement.</small>
</form>'''
    content=f'''
<div style="display:flex;justify-content:space-between;margin-bottom:18px" class="no-print">
  <a href="/facturation" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a>
  <button class="lt-btn lt-btn-outline lt-btn-sm" onclick="window.print()"><i class="bi bi-printer"></i> Imprimer</button>
</div>
<div class="lt-card" style="max-width:700px;margin:0 auto">
  <div class="lt-card-header" style="background:var(--grn-800)">
    <div style="display:flex;justify-content:space-between;align-items:center;width:100%">
      <div style="display:flex;align-items:center;gap:10px">
        <i class="fa-solid fa-house-medical" style="color:#fff;font-size:24px"></i>
        <div><div style="color:#fff;font-family:var(--font-display);font-size:16px;font-weight:700">Le Tropical</div><div style="color:rgba(255,255,255,.55);font-size:11px">Centre de Santé</div></div>
      </div>
      <div style="text-align:right;color:#fff"><div style="font-family:var(--font-display);font-size:18px">Facture N°{c["fid"]}</div><div style="font-size:12px;opacity:.65">{c["fd"]}</div></div>
    </div>
  </div>
  <div class="lt-card-body">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">
      <div><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:4px">Patient</div><div class="fw-600">{c["pat"]}</div><div class="text-muted">{c["nd"]}</div>{f'<div class="text-muted" style="font-size:12px">{c["pemail"]}</div>' if c["pemail"] else ""}</div>
      <div style="text-align:right"><div class="text-muted" style="font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:4px">Médecin</div><div class="fw-600">Dr. {c["med"]}</div><div class="text-muted">{c["spc"] or "Généraliste"}</div></div>
    </div>
    <div class="divider"></div>
    <table style="width:100%;border-collapse:collapse;margin:14px 0">
      <tr><td style="padding:8px 0">Consultation médicale — {c["rd"]}</td><td style="text-align:right;font-weight:600">{fcfa(c["mt"])}</td></tr>
      {f"<tr><td style='padding:8px 0;color:var(--text-muted)'>Prise en charge assurance ({ass['an']})</td><td style='text-align:right;color:var(--grn-600);font-weight:600'>- {fcfa(c['ma'])}</td></tr>" if ass and c['ma']>0 else ""}
    </table>
    <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:var(--surface);border-radius:10px;border:2px dashed var(--border)">
      <span class="font-display" style="font-size:16px;font-weight:700">MONTANT À PAYER</span>
      <span class="font-display text-danger" style="font-size:24px;font-weight:800">{fcfa(c["mp"])}</span>
    </div>
    <div style="text-align:center;margin-top:14px">{badge(c["fst"])}</div>
    {payer_form}
  </div>
</div>'''
    return layout(f'Facture N°{c["fid"]}', content, 'facturation')

@app.route('/facturation/<int:cid>/payer', methods=['POST'])
@login_required
@roles_allowed('admin','accueil')
def facture_payer(cid):
    f=request.form; mr=float(f.get('montant_recu',0) or 0); ma=float(f.get('montant_assurance',0) or 0)
    fact=q("SELECT montant_total FROM factures WHERE consultation_id=?",[cid],one=True)
    if not fact: flash('Facture introuvable.','error'); return redirect('/facturation')
    statut='payee' if mr>=(fact['montant_total']-ma) else 'partielle'
    ex("UPDATE factures SET montant_assurance=?,montant_patient=?,statut=? WHERE consultation_id=?",[ma,mr,statut,cid])
    pid_row=q("""SELECT r.patient_id FROM consultations c JOIN rendez_vous r ON c.rdv_id=r.id WHERE c.id=?""",[cid],one=True)
    if pid_row:
        if statut=='payee':
            add_notification(pid_row['patient_id'],'✅ Facture réglée',f'Votre facture N°{cid} a été réglée avec succès. Montant payé : {fcfa(mr)}. Merci.')
        else:
            add_notification(pid_row['patient_id'],'⚠️ Paiement partiel',f'Un paiement partiel de {fcfa(mr)} a été enregistré pour votre facture. Solde restant à régler.')
    flash(f'Paiement enregistré : {fcfa(mr)}. Statut : {statut}. Patient notifié.','success')
    return redirect('/facturation')

# ================================================================
# ASSURANCES
# ================================================================
@app.route('/assurances')
@login_required
@roles_allowed('admin','accueil')
def assurances():
    rows=q("SELECT * FROM assurances ORDER BY nom")
    trs=''.join(f'''<tr>
        <td><div class="fw-600">{a["nom"]}</div></td>
        <td>{"<span class='lt-badge lt-badge-planifie'>Publique</span>" if a["type"]=="Publique" else "<span class='lt-badge lt-badge-partielle'>Privée</span>"}</td>
        <td class="fw-600">{fcfa(a["plafond_annuel"])}</td>
        <td class="text-muted">{a["description"] or "—"}</td>
        <td><a href="/assurances/{a["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a></td>
    </tr>''' for a in rows) or '<tr><td colspan="5" style="text-align:center;padding:22px;color:var(--text-muted)">Aucune assurance</td></tr>'
    content=f'''
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
  <div class="page-title" style="margin:0"><i class="bi bi-shield-fill-check"></i> Assurances</div>
  <button class="lt-btn lt-btn-primary" onclick="document.getElementById('mAss').style.display='flex'"><i class="bi bi-plus-circle"></i> Nouvelle assurance</button>
</div>
<div class="lt-card">
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Assurance</th><th>Type</th><th>Plafond annuel</th><th>Description</th><th>Actions</th></tr></thead><tbody>{trs}</tbody></table></div>
</div>
<div id="mAss" style="display:none;position:fixed;inset:0;background:rgba(2,26,13,.55);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:16px;width:100%;max-width:440px;box-shadow:var(--shadow-lg)">
    <div style="padding:18px 24px;border-bottom:1px solid var(--border-light);display:flex;align-items:center;justify-content:space-between">
      <span class="font-display" style="font-size:16px;font-weight:600;color:var(--grn-800)"><i class="bi bi-shield-plus me-2"></i>Nouvelle Assurance</span>
      <button onclick="document.getElementById('mAss').style.display='none'" style="background:none;border:none;font-size:22px;cursor:pointer;color:#888">&times;</button>
    </div>
    <form method="POST" action="/assurances/new" style="padding:22px">
      <div class="mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" required></div>
      <div class="mb-3"><label class="lt-form-label">Type</label><select name="type" class="lt-form-control"><option value="Publique">Publique</option><option value="Privée">Privée</option></select></div>
      <div class="mb-3"><label class="lt-form-label">Plafond annuel (FCFA)</label><input type="number" name="plafond_annuel" class="lt-form-control" value="0" min="0" step="1000"></div>
      <div class="mb-3"><label class="lt-form-label">Description</label><textarea name="description" class="lt-form-control"></textarea></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Enregistrer</button>
        <button type="button" onclick="document.getElementById('mAss').style.display='none'" class="lt-btn lt-btn-outline">Annuler</button></div>
    </form>
  </div>
</div>'''
    return layout('Assurances', content, 'assurances')

@app.route('/assurances/new', methods=['POST'])
@login_required
@roles_allowed('admin','accueil')
def assurance_new():
    f=request.form
    ex("INSERT INTO assurances(nom,type,plafond_annuel,description) VALUES(?,?,?,?)",[f['nom'],f.get('type'),float(f.get('plafond_annuel',0)),f.get('description')])
    flash('Assurance ajoutée.','success'); return redirect('/assurances')

@app.route('/assurances/<int:aid>/edit', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil')
def assurance_edit(aid):
    a=q("SELECT * FROM assurances WHERE id=?",[aid],one=True)
    if not a: flash('Assurance introuvable.','error'); return redirect('/assurances')
    if request.method=='POST':
        f=request.form
        ex("UPDATE assurances SET nom=?,type=?,plafond_annuel=?,description=? WHERE id=?",[f['nom'],f.get('type'),float(f.get('plafond_annuel',0)),f.get('description'),aid])
        flash('Assurance mise à jour.','success'); return redirect('/assurances')
    content=f'''
<div class="mb-3"><a href="/assurances" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:500px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-pencil-square"></i> Modifier Assurance</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="mb-3"><label class="lt-form-label">Nom *</label><input type="text" name="nom" class="lt-form-control" value="{a["nom"]}" required></div>
    <div class="mb-3"><label class="lt-form-label">Type</label><select name="type" class="lt-form-control"><option {"selected" if a["type"]=="Publique" else ""} value="Publique">Publique</option><option {"selected" if a["type"]=="Privée" else ""} value="Privée">Privée</option></select></div>
    <div class="mb-3"><label class="lt-form-label">Plafond annuel (FCFA)</label><input type="number" name="plafond_annuel" class="lt-form-control" value="{a["plafond_annuel"]}" step="1000"></div>
    <div class="mb-3"><label class="lt-form-label">Description</label><textarea name="description" class="lt-form-control">{a["description"] or ""}</textarea></div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Mettre à jour</button><a href="/assurances" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Modifier Assurance', content, 'assurances')

@app.route('/assurances/patient/<int:pid>/add', methods=['GET','POST'])
@login_required
@roles_allowed('admin','accueil')
def patient_assurance_add(pid):
    p=q("SELECT * FROM patients WHERE id=?",[pid],one=True)
    ass=q("SELECT * FROM assurances ORDER BY nom")
    if not p: flash('Patient introuvable.','error'); return redirect('/patients')
    if request.method=='POST':
        f=request.form
        ex("INSERT INTO patient_assurance(patient_id,assurance_id,numero_contrat,taux_prise_en_charge,date_debut,date_fin) VALUES(?,?,?,?,?,?)",
           [pid,f['assurance_id'],f.get('numero_contrat'),float(f.get('taux',0)),f.get('date_debut') or None,f.get('date_fin') or None])
        flash('Assurance liée au patient.','success'); return redirect(f'/patients/{pid}')
    ass_opts='<option value="">— Choisir —</option>'+''.join(f'<option value="{a["id"]}">{a["nom"]} ({a["type"]})</option>' for a in ass)
    content=f'''
<div class="mb-3"><a href="/patients/{pid}" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:540px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-shield-plus"></i> Assurance pour {p["prenom"]} {p["nom"]}</span></div>
  <div class="lt-card-body"><form method="POST">
    <div class="mb-3"><label class="lt-form-label">Assurance *</label><select name="assurance_id" class="lt-form-control" required>{ass_opts}</select></div>
    <div class="mb-3"><label class="lt-form-label">N° Contrat</label><input type="text" name="numero_contrat" class="lt-form-control" placeholder="CTR-XXXX"></div>
    <div class="mb-3"><label class="lt-form-label">Taux de prise en charge (%)</label><input type="number" name="taux" class="lt-form-control" value="0" min="0" max="100"></div>
    <div class="row">
      <div class="col-6 mb-3"><label class="lt-form-label">Date début</label><input type="date" name="date_debut" class="lt-form-control"></div>
      <div class="col-6 mb-3"><label class="lt-form-label">Date fin</label><input type="date" name="date_fin" class="lt-form-control"></div>
    </div>
    <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary"><i class="bi bi-check2"></i> Enregistrer</button><a href="/patients/{pid}" class="lt-btn lt-btn-outline">Annuler</a></div>
  </form></div>
</div>'''
    return layout('Ajouter Assurance Patient', content, 'assurances')

# ================================================================
# TÉLÉCONSULTATION
# ================================================================
@app.route('/teleconsultation')
@login_required
def teleconsultation():
    role=session.get('user_role'); mid=session.get('medecin_id')
    if role=='medecin' and mid:
        rows=q("""SELECT t.*,r.date,r.heure,r.patient_id,p.nom||' '||p.prenom pat,m.nom||' '||m.prenom med FROM teleconsultations t JOIN rendez_vous r ON t.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id WHERE r.medecin_id=? ORDER BY r.date DESC""",[mid])
    else:
        rows=q("""SELECT t.*,r.date,r.heure,r.patient_id,p.nom||' '||p.prenom pat,m.nom||' '||m.prenom med FROM teleconsultations t JOIN rendez_vous r ON t.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id ORDER BY r.date DESC""")
    trs=''.join(f'''<tr>
        <td><b>{tc["date"]}</b> <small class="text-muted">{tc["heure"]}</small></td>
        <td>{tc["pat"]}</td><td>Dr. {tc["med"]}</td>
        <td>{badge(tc["statut"])}</td>
        <td>{tc["duree_minutes"] or "—"} min</td>
        <td>{f"<a href='{tc['lien_session']}' target='_blank' class='lt-btn lt-btn-primary lt-btn-xs'><i class='bi bi-camera-video-fill me-1'></i>Rejoindre</a>" if tc['lien_session'] else "<span class='text-muted'>—</span>"}</td>
        <td><a href="/teleconsultation/{tc["id"]}/edit" class="lt-btn lt-btn-outline lt-btn-xs"><i class="bi bi-pencil"></i></a></td>
    </tr>''' for tc in rows) or '<tr><td colspan="7" style="text-align:center;padding:22px;color:var(--text-muted)">Aucune téléconsultation</td></tr>'
    content=f'''
<div class="page-title"><i class="bi bi-camera-video-fill"></i> Téléconsultations</div>
<div class="lt-alert lt-alert-info mb-3"><i class="bi bi-info-circle-fill"></i><div>Pour créer une session, allez dans <a href="/rendez-vous/new"><b>Rendez-vous → Nouveau</b></a> et choisissez le type <em>Téléconsultation 📹</em>. Ajoutez ensuite le lien Meet ici pour notifier le patient.</div></div>
<div class="lt-card">
  <div class="lt-table-responsive"><table class="lt-table"><thead><tr><th>Date/Heure</th><th>Patient</th><th>Médecin</th><th>Statut</th><th>Durée</th><th>Session</th><th>Actions</th></tr></thead><tbody>{trs}</tbody></table></div>
  <div class="lt-card-footer">{len(rows)} session(s) · Le patient est notifié quand le lien Meet est enregistré</div>
</div>'''
    return layout('Téléconsultations', content, 'teleconsultation')

@app.route('/teleconsultation/<int:tid>/edit', methods=['GET','POST'])
@login_required
def teleconsultation_edit(tid):
    tc=q("""SELECT t.*,r.date,r.heure,r.patient_id,p.nom||' '||p.prenom pat,m.nom||' '||m.prenom med FROM teleconsultations t JOIN rendez_vous r ON t.rdv_id=r.id JOIN patients p ON r.patient_id=p.id JOIN medecins m ON r.medecin_id=m.id WHERE t.id=?""",[tid],one=True)
    if not tc: flash('Téléconsultation introuvable.','error'); return redirect('/teleconsultation')
    if request.method=='POST':
        f=request.form
        new_lien = f.get('lien_session','').strip()
        ex("UPDATE teleconsultations SET lien_session=?,statut=?,duree_minutes=?,notes=? WHERE id=?",[new_lien or None,f.get('statut'),f.get('duree_minutes') or None,f.get('notes'),tid])
        if new_lien and new_lien != (tc['lien_session'] or ''):
            msg = (f"Votre téléconsultation avec Dr. {tc['med']} est confirmée.\n"
                   f"📅 Date : {tc['date']} à {tc['heure']}\n"
                   f"🔗 Lien de connexion : {new_lien}\n"
                   f"Rejoignez la session à l'heure prévue.")
            add_notification(tc['patient_id'],'📹 Lien téléconsultation disponible', msg)
            flash(f'Téléconsultation mise à jour. Patient notifié avec le lien Meet.','success')
        else:
            flash('Téléconsultation mise à jour.','success')
        return redirect('/teleconsultation')
    so=''.join(f'<option value="{v}" {"selected" if tc["statut"]==v else ""}>{l}</option>' for v,l in [('planifiee','Planifiée'),('en_cours','En cours'),('terminee','Terminée'),('annulee','Annulée')])
    content=f'''
<div class="mb-3"><a href="/teleconsultation" class="lt-btn lt-btn-outline lt-btn-sm"><i class="bi bi-arrow-left"></i> Retour</a></div>
<div class="lt-card" style="max-width:600px">
  <div class="lt-card-header"><span class="lt-card-title"><i class="bi bi-camera-video-fill"></i> Modifier Téléconsultation N°{tid}</span></div>
  <div class="lt-card-body">
    <div class="lt-alert lt-alert-info mb-3"><i class="bi bi-person-fill"></i><b>{tc["pat"]}</b> → Dr. {tc["med"]} · {tc["date"]} {tc["heure"]}</div>
    <div class="lt-alert lt-alert-success mb-3"><i class="bi bi-bell-fill"></i><div>Le patient recevra une notification automatique dès que vous enregistrez un lien de session.</div></div>
    <form method="POST">
      <div class="mb-3">
        <label class="lt-form-label">Lien de session Google Meet (URL) *</label>
        <input type="url" name="lien_session" class="lt-form-control" value="{tc["lien_session"] or ""}" placeholder="https://meet.google.com/abc-defg-hij">
        <small class="text-muted">Le patient sera notifié avec ce lien dès la sauvegarde.</small>
      </div>
      <div class="mb-3"><label class="lt-form-label">Statut</label><select name="statut" class="lt-form-control">{so}</select></div>
      <div class="mb-3"><label class="lt-form-label">Durée (minutes)</label><input type="number" name="duree_minutes" class="lt-form-control" value="{tc["duree_minutes"] or ""}" min="1"></div>
      <div class="mb-3"><label class="lt-form-label">Notes de séance</label><textarea name="notes" class="lt-form-control">{tc["notes"] or ""}</textarea></div>
      <div style="display:flex;gap:10px"><button type="submit" class="lt-btn lt-btn-primary">Mettre à jour &amp; Notifier patient</button><a href="/teleconsultation" class="lt-btn lt-btn-outline">Annuler</a></div>
    </form>
  </div>
</div>'''
    return layout('Modifier Téléconsultation', content, 'teleconsultation')
try:
    init_db()
except Exception as _e:
    import traceback
    traceback.print_exc()
# ================================================================
# MAIN
# ================================================================
if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
