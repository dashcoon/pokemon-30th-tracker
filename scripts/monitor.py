import json, re, time, datetime, pathlib, requests
from bs4 import BeautifulSoup
ROOT=pathlib.Path(__file__).resolve().parents[1]
CAT=json.loads((ROOT/'data/catalog.json').read_text())
FEED=ROOT/'data/feed.json';HIST=ROOT/'data/history.json';SERIES=ROOT/'data/price-history.json'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def read(p,default):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,ValueError):return default
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def nodes(o):
 if isinstance(o,list):
  for x in o:yield from nodes(x)
 elif isinstance(o,dict):
  if '@graph' in o:yield from nodes(o['@graph'])
  yield o
def same(expected,actual):
 a=re.sub(r'[^a-z0-9]+',' ',str(actual).lower())
 e=re.sub(r'[^a-z0-9]+',' ',expected.lower())
 if not ('30th' in a or 'celebration' in a):return False
 for token in ('nidorina','lucario','exeggutor','espeon','umbreon','greninja','sylveon','mewtwo','ditto'):
  if token in e and token not in a:return False
 for token in ('elite trainer box','booster bundle','ultra premium collection','figure collection','tech sticker'):
  if token in e and token not in a:return False
 if 'pok mon day' in e and not ('day' in a or 'espeon' in a):return False
 if 'pok mon night' in e and not ('night' in a or 'umbreon' in a):return False
 return True
def check(item,session):
 out={**item,'checked_at':now(),'state':'unverified','price_dkk':None,'availability':'unknown','reason':'No matching product-specific structured offer'}
 try:
  r=session.get(item['url'],timeout=12,headers={'User-Agent':'Mozilla/5.0 (compatible; Pokemon30PriceMonitor/1.0)'})
  out['http_status']=r.status_code
  if r.status_code!=200:out['reason']='HTTP '+str(r.status_code);return out
  if 'html' not in r.headers.get('Content-Type','').lower():out['reason']='Non-HTML response';return out
  soup=BeautifulSoup(r.text[:2000000],'html.parser');found=set()
  for script in soup.select('script[type="application/ld+json"]'):
   try:
    for n in nodes(json.loads(script.string or script.get_text())):
     t=n.get('@type',[]);t=[t] if isinstance(t,str) else t
     if 'Product' not in t or not same(item['product'],n.get('name','')):continue
     offers=n.get('offers',[]);offers=[offers] if isinstance(offers,dict) else offers
     for o in offers:
      if not isinstance(o,dict) or o.get('priceCurrency','DKK')!='DKK':continue
      try:p=round(float(str(o.get('price','')).replace(',','.')),2)
      except (ValueError,TypeError):continue
      a=str(o.get('availability','')).rsplit('/',1)[-1].lower()
      if 0<p<100000 and a in ('instock','outofstock','preorder','presale','limitedavailability','soldout'):found.add((p,a))
   except (ValueError,TypeError):pass
  if len(found)==1:
   p,a=found.pop();out.update(state='verified_structured',price_dkk=p,availability=a,reason='Matching product JSON-LD offer; checkout not independently verified')
  elif len(found)>1:out['reason']='Conflicting structured offers'
 except requests.RequestException as e:out['reason']='Network error: '+type(e).__name__
 return out
def main():
 old={o['id']:o for o in read(FEED,{}).get('offers',[])}
 history=read(HIST,[]);series=read(SERIES,[]);session=requests.Session();offers=[];changes=[]
 for item in CAT['listings']:
  x=check(item,session);prev=old.get(x['id'])
  if x['state']=='verified_structured' and prev and prev.get('state')=='verified_structured' and (x['price_dkk'],x['availability'])!=(prev.get('price_dkk'),prev.get('availability')):
   event={'at':now(),'id':x['id'],'shop':x['shop'],'product':x['product'],'before':{'price_dkk':prev['price_dkk'],'availability':prev['availability']},'after':{'price_dkk':x['price_dkk'],'availability':x['availability']}}
   history.append(event);changes.append(event)
  if x['state']!='verified_structured' and prev and prev.get('state')=='verified_structured':x['last_verified']={'price_dkk':prev['price_dkk'],'availability':prev['availability'],'checked_at':prev['checked_at']}
  offers.append(x);time.sleep(.5)
 for x in offers:
  if x['state']=='verified_structured':
   series.append({'at':x['checked_at'],'id':x['id'],'product':x['product'],'shop':x['shop'],'price_dkk':x['price_dkk'],'availability':x['availability']})
 # Keep up to one year of verified observations; no fabricated historical prices.
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=365)).isoformat()
 series=[x for x in series if x.get('at','')>=cutoff]
 feed={'schema':1,'generated_at':now(),'source':'GitHub Actions automated retailer check','personal_data_included':False,'products':CAT['products'],'retailers':CAT['retailers'],'offers':offers,'recent_changes':history[-50:],'price_history':series,'summary':{'checked':len(offers),'verified':sum(x['state']=='verified_structured' for x in offers),'unverified':sum(x['state']!='verified_structured' for x in offers),'new_changes':len(changes)}}
 save(FEED,feed);save(HIST,history[-2000:]);save(SERIES,series);print(feed['summary'])
if __name__=='__main__':main()
