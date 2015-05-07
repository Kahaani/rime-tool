#!/usr/bin/env python3
import os, sqlite3, logging, collections, itertools, sys, re
import glob, fnmatch
import yaml 

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)

schemas = fnmatch.filter(sys.argv[1:], "*.schema.yaml")
if len(schemas) == 0:
    logging.info("請指定方案集schema.yaml文件！")
    exit(0)
else:
    logging.info("使用指定方案集:%s", schemas)

DB = 'trime.db'
if os.path.exists(DB): os.remove(DB)
conn = sqlite3.connect(DB)
cursor = conn.cursor()

logging.info("essay詞庫")
d=collections.defaultdict(int)
for i in open("brise/essay.txt", encoding="U8"):
    i=i.strip()
    if i:
        hz,weight=i.split()
        d[hz]=int(weight)

logging.info("OpenCC轉換")
opencc_dir = "OpenCC/data/dictionary/"
cursor.execute("CREATE VIRTUAL TABLE opencc USING fts3(s, t, r)")

for fn in ("TSCharacters.txt", "TSPhrases.txt", "STCharacters.txt", "STPhrases.txt", \
              "TWVariantsRevPhrases.txt", "HKVariantsRevPhrases.txt"):
    r = fn[:2].lower()
    if r in ("tw", "hk"): r = r + "2t"
    else: r = "%s2%s" % (r[0], r[1])
    for i in open(opencc_dir + fn, encoding="U8"):
        i = i.strip()
        if i:
            a = i.split('\t')
            cursor.execute('insert into opencc values (?, ?, "%s")' % r, a)

for fn in ("TWVariants.txt", "HKVariants.txt", "HKVariantsPhrases.txt", "JPVariants.txt", \
             "TWPhrasesIT.txt", "TWPhrasesName.txt", "TWPhrasesOther.txt"):
    r = fn[:3].lower().rstrip('v')
    for i in open(opencc_dir + fn, encoding="U8"):
        i = i.strip()
        if i:
            a = i.split('\t')
            cursor.execute('insert into opencc values (?,?,"t2%s")' % r, a)
            cursor.execute('insert into opencc values (?,?,"%s2t")' % r, a[::-1])

logging.info("方案")
sql = """
CREATE TABLE schema (
    "_id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "schema_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "full" TEXT NOT NULL
)"""
cursor.execute(sql)

dicts=set()
count = 0

def getdictname(fn, dic):
    bn = dic + ".dict.yaml"
    path = os.path.dirname(fn)
    fn = os.path.join(path, bn)
    if not os.path.exists(fn):
        fns = glob.glob("./brise/*/%s" % bn)
        if fns:
            return fns[0]
    return fn

for fn in schemas:
    yy = yaml.load(open(fn, encoding="U8").read().replace("\t", " "))
    l = [count]
    dicts.add(getdictname(fn, yy["translator"]["dictionary"]))
    l.append(yy["schema"]["schema_id"])
    l.append(yy["schema"]["name"])
    l.append(yaml.dump(yy))
    cursor.execute('insert into schema values (?,?,?,?)', l)
    count += 1
    logging.info("\t%s", yy["schema"]["name"])

logging.info("碼表")

for fn in dicts:
    hz = []
    zd = collections.defaultdict(list)
    mbStart = "..."
    isMB = False
    y = ""
    phrase = set()

    for line in open(fn, encoding="U8"):
        if not isMB:
            y+=line
        line = line.strip()
        if line.startswith(mbStart):
            isMB = True
            yy=yaml.load(y.replace("\t", " "))
            if yy.get("use_preset_vocabulary", False):
                phrase = set(filter(lambda x:1<len(x)<=yy.get("max_phrase_length", 6) and d[x]>=yy.get("min_phrase_weight", 1000), d.keys()))
            continue
        if isMB and line and not line.startswith("#"):
            fs = line.split("\t")
            l = len(fs)
            if l == 1:
                phrase.add(fs[0])
            elif l > 1:
                hz.append(fs[0:2])
                if len(fs[0]) > 1 and fs[0] in phrase:
                    phrase.remove(fs[0])
                if l == 2:
                    zd[fs[0]].append(fs[1])
                elif l == 3:
                    if not fs[2].startswith("0"):
                        zd[fs[0]].append(fs[1])
                        if "%" not in fs[2]:
                            d[fs[0]] = int(float(fs[2]))
    for p in phrase:
        pp = list(map(lambda x: zd.get(x, False), p))
        if all(pp):        
            for i in itertools.product(*pp):
                hz.append([p," ".join(i)])

    if yy.get("sort", "original") == "by_weight":
        hz.sort(key=lambda x: d[x[0]] if d[x[0]] > 0 else 1000, reverse = True)

    table = yy.get("name", os.path.basename(fn).split(".")[0])
    cursor.execute('CREATE VIRTUAL TABLE "%s" USING fts3(hz, py, tokenize=simple)' % table)
    py2ipa = yy.get("py2ipa", [])
    for i in hz:
        sql = 'insert into %s values (?, ?)' % table
        for j in py2ipa:
            r = re.split("(?<!\\\\)/", j)
            if r[0] == "xlit":
                for a,b in zip(r[1].replace("\\",""),r[2].replace("\\","")):
                    i[1]=i[1].replace(a,b)
        cursor.execute(sql, i)
    logging.info("\t%s 詞條数 %d", table, len(hz))

conn.commit()
conn.close()
