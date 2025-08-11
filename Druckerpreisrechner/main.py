#!/usr/bin/env python3
# main.py - Druckerpreisrechner (Comfort-Version)
# Funktionen:
# - Drucker & Verbrauchsmaterial verwalten (SQLite)
# - Automatische Übernahme von Cyan->Magenta/Yellow beim Anlegen
# - Suche/Filter, CSV-Export, Profile speichern/laden
# - Vergleich mit einstellbarem Deckungsgrad (S/W & Farbe) und Farbanteil
# - Break-even (Seiten) gegenüber dem günstigsten Anschaffungspreis
#
# Starte mit: python main.py
# Die SQLite DB (database.db) wird im selben Ordner angelegt.

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3, os, csv
from decimal import Decimal, InvalidOperation

DB_FILE = "database.db"

# -------------------------
# DB SETUP
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model TEXT UNIQUE NOT NULL,
        price REAL NOT NULL,
        is_color INTEGER NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS consumables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        printer_id INTEGER NOT NULL,
        kleur TEXT NOT NULL,
        price REAL NOT NULL,
        reach INTEGER NOT NULL,
        UNIQUE(printer_id,kleur)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        cov_sw REAL NOT NULL,
        cov_color REAL NOT NULL,
        color_share REAL NOT NULL
    )""")
    conn.commit()
    conn.close()

# -------------------------
# Helpers
# -------------------------
def to_float(val, default=0.0):
    try:
        return float(str(val).strip().replace(',', '.'))
    except Exception:
        return default

def to_int(val, default=0):
    try:
        return int(float(str(val).strip().replace(',', '.')))
    except Exception:
        return default

# -------------------------
# DB Operations
# -------------------------
def add_printer_db(model, price, is_color):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT INTO printers (model,price,is_color) VALUES (?,?,?)", (model, price, 1 if is_color else 0))
    conn.commit(); conn.close()

def update_printer_db(pid, model, price, is_color):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("UPDATE printers SET model=?, price=?, is_color=? WHERE id=?", (model, price, 1 if is_color else 0, pid))
    conn.commit(); conn.close()

def delete_printer_db(pid):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("DELETE FROM consumables WHERE printer_id=?", (pid,))
    c.execute("DELETE FROM printers WHERE id=?", (pid,))
    conn.commit(); conn.close()

def list_printers_db(search_filter=None):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    if search_filter:
        like = f"%{search_filter}%"
        c.execute("SELECT id,model,price,is_color FROM printers WHERE model LIKE ? ORDER BY model", (like,))
    else:
        c.execute("SELECT id,model,price,is_color FROM printers ORDER BY model")
    rows = c.fetchall(); conn.close(); return rows

def get_printer_db(pid):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT id,model,price,is_color FROM printers WHERE id=?", (pid,))
    r = c.fetchone(); conn.close(); return r

def add_consumable_db(printer_id, kleur, price, reach):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO consumables (printer_id,kleur,price,reach) VALUES (?,?,?,?)", (printer_id, kleur, price, reach))
    conn.commit(); conn.close()

def delete_consumable_db(cid):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("DELETE FROM consumables WHERE id=?", (cid,))
    conn.commit(); conn.close()

def list_consumables_db(printer_id=None):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    if printer_id:
        c.execute("SELECT id,printer_id,kleur,price,reach FROM consumables WHERE printer_id=? ORDER BY kleur", (printer_id,))
    else:
        c.execute("SELECT id,printer_id,kleur,price,reach FROM consumables ORDER BY printer_id,kleur")
    rows = c.fetchall(); conn.close(); return rows

def get_consumable_db(printer_id, kleur):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT price,reach FROM consumables WHERE printer_id=? AND kleur=?", (printer_id,kleur))
    r = c.fetchone(); conn.close(); return r

def save_profile_db(name, cov_sw, cov_color, color_share):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO profiles (name,cov_sw,cov_color,color_share) VALUES (?,?,?,?)", (name, cov_sw, cov_color, color_share))
    conn.commit(); conn.close()

def load_profiles_db():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT id,name,cov_sw,cov_color,color_share FROM profiles ORDER BY name")
    rows = c.fetchall(); conn.close(); return rows

# -------------------------
# Calc logic
# -------------------------
def compute_costs_for_printer(printer_id, cov_sw_pct, cov_color_pct):
    p = get_printer_db(printer_id)
    if not p: return (None,None,{"error":"Drucker nicht gefunden"})
    _, model, price, is_color = p
    black = get_consumable_db(printer_id, "Schwarz")
    if not black:
        return (None,None,{"error":"Kein schwarzes Verbrauchsmaterial eingetragen"})
    price_black, reach_black = black
    reach_black = max(1, int(reach_black))
    cost_black_per_5 = float(price_black) / reach_black
    sw_page_cost = cost_black_per_5 * (cov_sw_pct / 5.0)
    color_page_cost = None
    if is_color:
        c_col = get_consumable_db(printer_id, "Cyan")
        m_col = get_consumable_db(printer_id, "Magenta")
        y_col = get_consumable_db(printer_id, "Yellow")
        base = None
        for x in (c_col, m_col, y_col):
            if x:
                base = x; break
        if not base:
            return (sw_page_cost, None, {"error":"Keine Farbverbrauchsmaterialien eingetragen"})
        prices = {}
        reaches = {}
        for name, raw in (("Cyan", c_col), ("Magenta", m_col), ("Yellow", y_col)):
            if raw:
                prices[name] = float(raw[0]); reaches[name] = max(1,int(raw[1]))
            else:
                prices[name] = float(base[0]); reaches[name] = max(1,int(base[1]))
        cost_black_at_color = cost_black_per_5 * (cov_color_pct / 5.0)
        color_components = 0.0
        for name in ("Cyan","Magenta","Yellow"):
            cost_per_5 = prices[name] / reaches[name]
            color_components += cost_per_5 * (cov_color_pct / 5.0)
        color_page_cost = cost_black_at_color + color_components
    else:
        color_page_cost = sw_page_cost
    return (sw_page_cost, color_page_cost, {"model":model, "is_color":bool(is_color)})

# -------------------------
# App UI
# -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Druckerpreisrechner (Comfort)")
        self.geometry("1100x700")
        nb = ttk.Notebook(self)
        self.tab_manage = ttk.Frame(nb)
        self.tab_material = ttk.Frame(nb)
        self.tab_compare = ttk.Frame(nb)
        nb.add(self.tab_manage, text="Drucker verwalten")
        nb.add(self.tab_material, text="Verbrauchsmaterial")
        nb.add(self.tab_compare, text="Preisvergleich")
        nb.pack(fill="both", expand=True)
        self.build_manage_tab()
        self.build_material_tab()
        self.build_compare_tab()
        self.refresh_printers()

    # Manage Tab
    def build_manage_tab(self):
        frm = ttk.Frame(self.tab_manage); frm.pack(fill="both", expand=True, padx=10, pady=10)
        left = ttk.Frame(frm); left.pack(side="left", fill="y", padx=10)
        ttk.Label(left, text="Drucker anlegen / bearbeiten").pack(anchor="w")
        ttk.Label(left, text="Modell:").pack(anchor="w"); self.e_model = ttk.Entry(left); self.e_model.pack(fill="x")
        ttk.Label(left, text="Anschaffungspreis (EUR):").pack(anchor="w"); self.e_price = ttk.Entry(left); self.e_price.pack(fill="x")
        self.var_is_color = tk.IntVar(); ttk.Checkbutton(left, text="Farbdrucker", variable=self.var_is_color).pack(anchor="w")
        ttk.Button(left, text="Hinzufügen", command=self.add_printer).pack(fill="x", pady=5)
        ttk.Button(left, text="Update (ausgewählt)", command=self.update_selected_printer).pack(fill="x")
        ttk.Button(left, text="Löschen (ausgewählt)", command=self.delete_selected_printer).pack(fill="x", pady=5)
        ttk.Separator(left).pack(fill="x", pady=10)
        ttk.Label(left, text="Suche Modell: ").pack(anchor="w"); self.e_search = ttk.Entry(left); self.e_search.pack(fill="x")
        self.e_search.bind("<KeyRelease>", lambda e: self.refresh_printers())
        ttk.Button(left, text="Exportiere Druckerliste (CSV)", command=self.export_printers_csv).pack(fill="x", pady=5)

        right = ttk.Frame(frm); right.pack(side="left", fill="both", expand=True)
        cols = ("id","model","price","is_color")
        self.tree_printers = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        self.tree_printers.heading("id", text="#"); self.tree_printers.column("id", width=40)
        self.tree_printers.heading("model", text="Modell"); self.tree_printers.column("model", width=350)
        self.tree_printers.heading("price", text="Anschaffung (EUR)"); self.tree_printers.column("price", width=140)
        self.tree_printers.heading("is_color", text="Farbe"); self.tree_printers.column("is_color", width=80)
        self.tree_printers.pack(fill="both", expand=True)
        self.tree_printers.bind("<Double-1>", lambda e: self.load_selected_printer_into_form())

    def add_printer(self):
        model = self.e_model.get().strip()
        if not model:
            messagebox.showerror("Fehler","Modell darf nicht leer sein"); return
        try:
            price = float(self.e_price.get().strip().replace(",", "."))
        except Exception:
            messagebox.showerror("Fehler","Ungültiger Preis"); return
        is_color = bool(self.var_is_color.get())
        try:
            add_printer_db(model, price, is_color)
        except Exception as e:
            messagebox.showerror("Fehler","Konnte Drucker nicht anlegen:\n"+str(e))
        self.e_model.delete(0,tk.END); self.e_price.delete(0,tk.END); self.var_is_color.set(0)
        self.refresh_printers()

    def refresh_printers(self):
        for i in self.tree_printers.get_children(): self.tree_printers.delete(i)
        filt = self.e_search.get().strip() if hasattr(self,'e_search') else None
        for row in list_printers_db(filt):
            pid, model, price, is_color = row
            self.tree_printers.insert('',tk.END, values=(pid, model, f"{price:.2f}", "Ja" if is_color else "Nein"))
        self.refresh_printer_comboboxes()

    def load_selected_printer_into_form(self):
        sel = self.tree_printers.selection()
        if not sel: return
        pid = int(self.tree_printers.item(sel[0])['values'][0])
        p = get_printer_db(pid)
        if not p: return
        _, model, price, is_color = p
        self.e_model.delete(0,tk.END); self.e_model.insert(0, model)
        self.e_price.delete(0,tk.END); self.e_price.insert(0, f"{price:.2f}")
        self.var_is_color.set(1 if is_color else 0)

    def update_selected_printer(self):
        sel = self.tree_printers.selection()
        if not sel: messagebox.showinfo("Info","Kein Drucker ausgewählt"); return
        pid = int(self.tree_printers.item(sel[0])['values'][0])
        model = self.e_model.get().strip()
        try:
            price = float(self.e_price.get().strip().replace(",", "."))
        except Exception:
            messagebox.showerror("Fehler","Ungültiger Preis"); return
        if not model:
            messagebox.showerror("Fehler","Ungültige Eingaben"); return
        update_printer_db(pid, model, price, bool(self.var_is_color.get()))
        self.refresh_printers()

    def delete_selected_printer(self):
        sel = self.tree_printers.selection()
        if not sel: messagebox.showinfo("Info","Kein Drucker ausgewählt"); return
        pid = int(self.tree_printers.item(sel[0])['values'][0])
        if not messagebox.askyesno("Löschen?", "Drucker und zugehöriges Material löschen?"): return
        delete_printer_db(pid); self.refresh_printers()

    # Material tab
    def build_material_tab(self):
        frm = ttk.Frame(self.tab_material); frm.pack(fill="both", expand=True, padx=10, pady=10)
        left = ttk.Frame(frm); left.pack(side="left", fill="y", padx=10)
        ttk.Label(left, text="Verbrauchsmaterial hinzufügen").pack(anchor="w")
        ttk.Label(left, text="Drucker:").pack(anchor="w"); self.cb_printer_for_mat = ttk.Combobox(left, state="readonly"); self.cb_printer_for_mat.pack(fill="x")
        ttk.Label(left, text="Farbe:").pack(anchor="w"); self.cb_color = ttk.Combobox(left, values=["Schwarz","Cyan","Magenta","Yellow"], state="readonly"); self.cb_color.pack(fill="x")
        ttk.Label(left, text="Preis (EUR):").pack(anchor="w"); self.e_mat_price = ttk.Entry(left); self.e_mat_price.pack(fill="x")
        ttk.Label(left, text="Reichweite (Seiten bei 5%):").pack(anchor="w"); self.e_mat_reach = ttk.Entry(left); self.e_mat_reach.pack(fill="x")
        ttk.Button(left, text="Hinzufügen/Update", command=self.add_consumable_ui).pack(fill="x", pady=5)
        ttk.Button(left, text="Wenn Cyan vorhanden: Magenta/Yellow übernehmen", command=self.autofill_from_cyan).pack(fill="x", pady=2)
        ttk.Button(left, text="Export Verbrauchsmaterial (CSV)", command=self.export_consumables_csv).pack(fill="x", pady=5)

        right = ttk.Frame(frm); right.pack(side="left", fill="both", expand=True)
        cols = ("id","printer","kleur","price","reach")
        self.tree_mat = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        self.tree_mat.heading("id", text="#"); self.tree_mat.column("id", width=40)
        self.tree_mat.heading("printer", text="Drucker"); self.tree_mat.column("printer", width=300)
        self.tree_mat.heading("kleur", text="Farbe"); self.tree_mat.column("kleur", width=100)
        self.tree_mat.heading("price", text="Preis (EUR)"); self.tree_mat.column("price", width=120)
        self.tree_mat.heading("reach", text="Reichweite (5%)"); self.tree_mat.column("reach", width=120)
        self.tree_mat.pack(fill="both", expand=True)
        ttk.Button(right, text="Löschen (ausgewählt)", command=self.delete_selected_consumable_ui).pack(pady=5)

    def refresh_printer_comboboxes(self):
        printers = list_printers_db()
        models = [r[1] for r in printers]
        self.printer_map = {r[1]: r[0] for r in printers}
        try:
            self.cb_printer_for_mat['values'] = models
            if models and (not self.cb_printer_for_mat.get()):
                self.cb_printer_for_mat.set(models[0])
        except Exception:
            pass
        try:
            # refresh compare listbox
            self.listbox_compare.delete(0,tk.END)
            for r in printers:
                self.listbox_compare.insert(tk.END, r[1])
        except Exception:
            pass
        self.refresh_material_tree()

    def add_consumable_ui(self):
        printer_name = self.cb_printer_for_mat.get().strip()
        if not printer_name:
            messagebox.showerror("Fehler","Keinen Drucker ausgewählt"); return
        pid = self.printer_map.get(printer_name)
        if pid is None:
            messagebox.showerror("Fehler","Drucker nicht gefunden"); return
        kleur = self.cb_color.get().strip()
        if not kleur:
            messagebox.showerror("Fehler","Keine Farbe gewählt"); return
        try:
            price = float(self.e_mat_price.get().strip().replace(",", "."))
            reach = int(float(self.e_mat_reach.get().strip().replace(",", ".")))
        except Exception:
            messagebox.showerror("Fehler","Ungültige Preis- oder Reichweitenangabe"); return
        if kleur=="Cyan" and get_printer_db(pid)[3]==1:
            yes = messagebox.askyesno("Vorschlag","Möchtest du Preis und Reichweite auch für Magenta und Yellow übernehmen? (Du kannst sie später individuell anpassen)")
            add_consumable_db(pid, "Cyan", price, reach)
            if yes:
                add_consumable_db(pid, "Magenta", price, reach)
                add_consumable_db(pid, "Yellow", price, reach)
        else:
            add_consumable_db(pid, kleur, price, reach)
        self.e_mat_price.delete(0,tk.END); self.e_mat_reach.delete(0,tk.END)
        self.refresh_material_tree()

    def refresh_material_tree(self):
        for i in self.tree_mat.get_children(): self.tree_mat.delete(i)
        v = self.cb_printer_for_mat.get().strip()
        pid = self.printer_map.get(v) if v else None
        rows = list_consumables_db(pid)
        pmap = {r[0]: r[1] for r in list_printers_db()}
        for r in rows:
            cid, prid, kleur, price, reach = r
            pname = pmap.get(prid, "??")
            self.tree_mat.insert("",tk.END, iid=str(cid), values=(cid, pname, kleur, f"{price:.2f}", reach))

    def delete_selected_consumable_ui(self):
        sel = self.tree_mat.selection()
        if not sel: messagebox.showinfo("Info","Kein Verbrauchsmaterial gewählt"); return
        cid = int(sel[0])
        if not messagebox.askyesno("Löschen?","Ausgewähltes Verbrauchsmaterial löschen?"): return
        delete_consumable_db(cid); self.refresh_material_tree()

    def autofill_from_cyan(self):
        pname = self.cb_printer_for_mat.get().strip()
        if not pname:
            messagebox.showerror("Fehler","Keinen Drucker gewählt"); return
        pid = self.printer_map.get(pname)
        if pid is None:
            messagebox.showerror("Fehler","Drucker nicht gefunden"); return
        c = get_consumable_db(pid, "Cyan")
        if not c:
            messagebox.showinfo("Info","Keine Cyan-Angabe vorhanden"); return
        price, reach = c
        add_consumable_db(pid, "Magenta", price, reach); add_consumable_db(pid, "Yellow", price, reach)
        messagebox.showinfo("OK","Magenta und Yellow wurden übernommen (falls fehlend)")
        self.refresh_material_tree()

    def export_printers_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")], title="Druckerliste speichern als")
        if not path: return
        rows = list_printers_db()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id","model","price","is_color"])
            for r in rows: w.writerow(r)
        messagebox.showinfo("Export", f"Druckerliste nach {path} exportiert.")

    def export_consumables_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")], title="Verbrauchsmaterial speichern als")
        if not path: return
        rows = list_consumables_db()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id","printer_id","color","price","reach"])
            for r in rows: w.writerow(r)
        messagebox.showinfo("Export", f"Verbrauchsmaterial nach {path} exportiert.")

    # Compare Tab
    def build_compare_tab(self):
        frm = ttk.Frame(self.tab_compare); frm.pack(fill="both", expand=True, padx=10, pady=10)
        left = ttk.Frame(frm); left.pack(side="left", fill="y", padx=10)
        ttk.Label(left, text="Wähle Drucker für Vergleich (Mehrfachauswahl)").pack(anchor="w")
        self.listbox_compare = tk.Listbox(left, selectmode="extended", width=40, height=12)
        self.listbox_compare.pack(fill="y")
        ttk.Button(left, text="Aktualisieren", command=self.refresh_printers).pack(fill="x", pady=5)
        ttk.Label(left, text="Deckungsgrade und Farbanteil").pack(anchor="w", pady=(10,0))
        ttk.Label(left, text="S/W Deckung (%)").pack(anchor="w"); self.e_cov_sw = ttk.Entry(left); self.e_cov_sw.insert(0,"5"); self.e_cov_sw.pack(fill="x")
        ttk.Label(left, text="Farbdeckung (%)").pack(anchor="w"); self.e_cov_color = ttk.Entry(left); self.e_cov_color.insert(0,"5"); self.e_cov_color.pack(fill="x")
        ttk.Label(left, text="Anteil Farbseiten (%)").pack(anchor="w"); self.e_color_share = ttk.Entry(left); self.e_color_share.insert(0,"50"); self.e_color_share.pack(fill="x")
        ttk.Button(left, text="Profil speichern", command=self.save_profile_ui).pack(fill="x", pady=5)
        ttk.Button(left, text="Profil laden", command=self.load_profile_ui).pack(fill="x", pady=2)
        ttk.Button(left, text="Vergleichen", command=self.run_compare).pack(fill="x", pady=10)
        ttk.Button(left, text="Exportiere Vergleich (CSV)", command=self.export_compare_csv).pack(fill="x")

        right = ttk.Frame(frm); right.pack(side="left", fill="both", expand=True)
        cols = ("model","price","sw_cost","color_cost","avg_cost","break_even")
        self.tree_compare = ttk.Treeview(right, columns=cols, show="headings")
        self.tree_compare.heading("model", text="Modell"); self.tree_compare.column("model", width=300)
        self.tree_compare.heading("price", text="Anschaffung (EUR)"); self.tree_compare.column("price", width=130)
        self.tree_compare.heading("sw_cost", text="Seitenpreis S/W (EUR)"); self.tree_compare.column("sw_cost", width=130)
        self.tree_compare.heading("color_cost", text="Seitenpreis Farbe (EUR)"); self.tree_compare.column("color_cost", width=140)
        self.tree_compare.heading("avg_cost", text="Durchschnittspreis (EUR)"); self.tree_compare.column("avg_cost", width=140)
        self.tree_compare.heading("break_even", text="Break-Even (Seiten) gegenüber günstigstem Anschaffungspreis"); self.tree_compare.column("break_even", width=220)
        self.tree_compare.pack(fill="both", expand=True)

    def save_profile_ui(self):
        name = simpledialog.askstring("Profilname", "Name für Profil eingeben:")
        if not name: return
        cov_sw = to_float(self.e_cov_sw.get(), None); cov_color = to_float(self.e_cov_color.get(), None); color_share = to_float(self.e_color_share.get(), None)
        if cov_sw is None or cov_color is None or color_share is None:
            messagebox.showerror("Fehler","Ungültige Werte"); return
        save_profile_db(name, cov_sw, cov_color, color_share)
        messagebox.showinfo("OK", "Profil gespeichert.")

    def load_profile_ui(self):
        profiles = load_profiles_db()
        if not profiles: messagebox.showinfo("Info","Keine Profile vorhanden"); return
        names = [p[1] for p in profiles]
        sel = simpledialog.askstring("Profil wählen", f"Verfügbare Profile: {', '.join(names)}\nGib den Profilnamen ein:")
        if not sel: return
        for p in profiles:
            if p[1]==sel:
                _,_,cov_sw,cov_color,color_share = p
                self.e_cov_sw.delete(0,tk.END); self.e_cov_sw.insert(0,str(cov_sw))
                self.e_cov_color.delete(0,tk.END); self.e_cov_color.insert(0,str(cov_color))
                self.e_color_share.delete(0,tk.END); self.e_color_share.insert(0,str(color_share))
                return
        messagebox.showerror("Fehler","Profil nicht gefunden")

    def run_compare(self):
        sel_idxs = self.listbox_compare.curselection()
        if not sel_idxs:
            messagebox.showinfo("Info","Keine Drucker gewählt"); return
        selected_models = [self.listbox_compare.get(i) for i in sel_idxs]
        printers = list_printers_db()
        model_to_id = {r[1]: r[0] for r in printers}
        selected_ids = [model_to_id[m] for m in selected_models if m in model_to_id]
        cov_sw = to_float(self.e_cov_sw.get(), None); cov_color = to_float(self.e_cov_color.get(), None); color_share = to_float(self.e_color_share.get(), None)
        if cov_sw is None or cov_color is None or color_share is None:
            messagebox.showerror("Fehler","Ungültige Deckungsangaben"); return
        rows = []
        for pid in selected_ids:
            p = get_printer_db(pid)
            if not p: continue
            _, model, price, is_color = p
            sw_cost, color_cost, info = compute_costs_for_printer(pid, cov_sw, cov_color)
            avg_cost = None
            if sw_cost is not None and color_cost is not None:
                avg_cost = (color_share/100.0)*color_cost + (1.0 - color_share/100.0)*sw_cost
            rows.append({"id":pid, "model":model, "price":price, "sw_cost":sw_cost, "color_cost":color_cost, "avg_cost":avg_cost})
        baseline = min(rows, key=lambda r: r["price"])
        baseline_price = baseline["price"]; baseline_avg = baseline["avg_cost"]
        for r in rows:
            be = "-"
            if r["id"]==baseline["id"]:
                be = "-"
            else:
                if r["avg_cost"] is None or baseline_avg is None:
                    be = "-"
                else:
                    if r["price"] > baseline_price and r["avg_cost"] < baseline_avg:
                        denom = (baseline_avg - r["avg_cost"])
                        if denom <= 0:
                            be = "-"
                        else:
                            pages = int((r["price"] - baseline_price) / denom) + 1
                            be = str(pages)
                    else:
                        be = "-"
            r["break_even"] = be
        for i in self.tree_compare.get_children(): self.tree_compare.delete(i)
        for r in rows:
            sws = f"{r['sw_cost']:.4f}" if r['sw_cost'] is not None else "n/a"
            cols = (r['model'], f"{r['price']:.2f}", sws, (f"{r['color_cost']:.4f}" if r['color_cost'] is not None else "n/a"), (f"{r['avg_cost']:.4f}" if r['avg_cost'] is not None else "n/a"), r['break_even'])
            self.tree_compare.insert("",tk.END, values=cols)
        self._last_compare_rows = rows

    def export_compare_csv(self):
        if not hasattr(self, '_last_compare_rows') or not self._last_compare_rows:
            messagebox.showinfo("Info","Keine Vergleichsdaten vorhanden. Bitte zuerst 'Vergleichen' ausführen."); return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")], title="Vergleich speichern als")
        if not path: return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["model","price","sw_cost","color_cost","avg_cost","break_even"])
            for r in self._last_compare_rows:
                w.writerow([r['model'], r['price'], r['sw_cost'] if r['sw_cost'] is not None else '', r['color_cost'] if r['color_cost'] is not None else '', r['avg_cost'] if r['avg_cost'] is not None else '', r['break_even']])
        messagebox.showinfo("Export", f"Vergleich nach {path} exportiert.")

# Run
def main():
    init_db()
    app = App()
    app.mainloop()

if __name__ == '__main__':
    main()
