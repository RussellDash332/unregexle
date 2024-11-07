import logging
import os
import platform
import re
import requests
import string
import sys
import time
from pprint import pprint
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

try:    TOKEN, CHATS = os.environ['TOKEN'], os.environ['CHATS']
except: from env import TOKEN, CHATS

logging.basicConfig(
    level=logging.INFO, 
    format= '[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)

# Constants
sys.setrecursionlimit(5000)
ATTEMPT_LIMIT = 1
try:
    with open('version.txt', 'r') as f:
        __VERSION__ = f.readline().split()[1]
except:
    __VERSION__ = None

def get_size():
    if len(sys.argv) == 1:  size = 3
    else:                   size = int(sys.argv[1])
    assert 1 <= size <= 32, 'Size must be between 1 and 32 exclusive'
    return size

def get_day():
    if len(sys.argv) < 3:   day = '' # today's
    else:                   day = int(sys.argv[2])
    return day

def loop_resolve(f, resolution, lim, *args):
    if lim == 0:
        raise Exception('Reached the limit for number of tries')
    try:
        return f(*args)
    except Exception as e:
        print(f'Issue found: {type(e).__name__}: {str(e)}')
        resolution()
        return loop_resolve(f, resolution, lim-1, *args)

def get_windows_browser():
    service = Service()
    options = webdriver.ChromeOptions()
    options.add_argument('--headless') # to debug, comment this line
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    browser = webdriver.Chrome(service=service, options=options)
    return browser

def get_linux_browser():
    version = __VERSION__
    if version == None: chrome_service = Service(ChromeDriverManager(chrome_type='chromium').install())
    else:               chrome_service = Service(ChromeDriverManager(chrome_type='chromium', driver_version=version).install())
    chrome_options = Options()
    options = [
        "--headless",
        "--disable-gpu",
        "--window-size=1920,1200",
        "--ignore-certificate-errors",
        "--disable-extensions",
        "--no-sandbox",
        "--disable-dev-shm-usage"
    ]
    for option in options: chrome_options.add_argument(option)
    browser = webdriver.Chrome(service=chrome_service, options=chrome_options)
    browser.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': 'Singapore'})
    return browser

def send(token, chat_id, bot_message):
    resp = requests.get(f'https://api.telegram.org/bot{token}/sendMessage', params={
        'chat_id': chat_id,
        'parse_mode': 'MarkdownV2',
        'text': bot_message,
        'disable_web_page_preview': False
        })
    logging.info(resp.json().get('description') if not resp.ok else resp.ok)

def parse(html, n=get_size()):
    def handle_qn(s):
        result = []
        for v in s:
            tmp = ['']
            for i in range(len(v)):
                if v[i] == '?': continue
                if i < len(v)-1 and v[i+1] == '?':
                    tmp = tmp + [x+v[i] for x in tmp]
                else:
                    tmp = [x+v[i] for x in tmp]
            result.extend(tmp)
        return result

    rules = {ax:{} for ax in 'xyz'}
    for hexagon in html.findAll('div', class_='hexagon_center'):
        for ax in 'xyz':
            for k in range(2*n-1):
                for rule in hexagon.findAll('div', id=f'rule_{ax}_{k}'):
                    text = rule.text.strip()
                    if text[0] == '.': # .*r1.*r2.*
                        rules[ax][k] = {'mode': 0, 'contains': [s for s in text.split('.*') if s]}
                    else: # (r1|r2|...)+
                        rules[ax][k] = {'mode': 1, 'candidates': handle_qn(text[1:-2].split('|'))}
    for ax in rules:
        rules[ax] = [rules[ax][k] for k in range(2*n-1)]
    return rules

def solve(rules, n=get_size()):
    def display():
        ans = []
        for i in range(2*n-1):
            for h in hexagons[i]: ans.append(h.get('v', '.'))
        return ''.join(ans)

    hexagons = [[{} for _ in range(2*n-1-abs(n-1-i))] for i in range(2*n-1)]
    reverse_map = {}

    # x axis
    for i in range(2*n-1):
        r = range(max(i-n+1, 0), min(2*n-1, n+i))
        idx = len(r)-1
        for j in r:
            hexagons[j][i-max(j-n+1, 0)]['x'] = (i, idx)
            reverse_map[('x', i, idx)] = (j, i-max(j-n+1, 0))
            idx -= 1

    # y axis
    for i in range(2*n-1):
        for j in range(2*n-1-abs(n-1-i)):
            hexagons[i][j]['y'] = (i, j)
            reverse_map[('y', i, j)] = (i, j)

    # z axis
    for i in range(2*n-1):
        r = range(max(i-n+1, 0), min(2*n-1, n+i))
        idx = len(r)-1
        for j in r:
            hexagons[-j-1][i-max(j-n+1, 0)]['z'] = (i, idx)
            reverse_map[('z', i, idx)] = ((-j-1)%(2*n-1), i-max(j-n+1, 0))
            idx -= 1

    # The strategy is that we try to keep using mode 1 to solve,
    # and then fill the gaps with mode 0
    for _ in range(2*n):
        # Start with the corner hexagons first
        pos = [(i, j) for i in (0, n-1, -1) for j in (0, -1)]
        for i, j in pos:
            for a, b in ('xy', 'xz', 'yz'):
                ia, pa = hexagons[i][j][a]; ra = rules[a][ia]
                ib, pb = hexagons[i][j][b]; rb = rules[b][ib]
                if ra['mode'] == rb['mode'] == 1:
                    check = set(c[-(pa!=0)] for c in ra['candidates'])&set(c[-(pb!=0)] for c in rb['candidates'])
                    if len(check) == 1:
                        v = check.pop()
                        wa = list(filter(lambda c: c[-(pa!=0)]==v, ra['candidates']))
                        wb = list(filter(lambda c: c[-(pb!=0)]==v, rb['candidates']))
                        if len(wa) == 1:
                            idx = pa
                            pos = -(pa!=0)
                            for _ in range(len(wa[0])):
                                ni, nj = reverse_map[(a, ia, idx)]
                                hexagons[ni][nj]['v'] = wa[0][pos]
                                idx += 2*(pa==0)-1
                                pos += 2*(pa==0)-1
                        if len(wb) == 1:
                            idx = pb
                            pos = -(pb!=0)
                            for _ in range(len(wb[0])):
                                ni, nj = reverse_map[(b, ib, idx)]
                                hexagons[ni][nj]['v'] = wb[0][pos]
                                idx += 2*(pb==0)-1
                                pos += 2*(pb==0)-1

        # Non-corner but outermost
        pos = [(i, j) for i in range(2*n-1) for j in range(len(hexagons[i])) if i in (0, 2*n-2) or j in (0, len(hexagons[i])-1)]
        for i, j in pos:
            for a, b in ('xy', 'xz', 'yz'):
                ia, pa = hexagons[i][j][a]; ra = rules[a][ia]
                ib, pb = hexagons[i][j][b]; rb = rules[b][ib]
                if not ((a, ia, pa-1) not in reverse_map or (a, ia, pa+1) not in reverse_map) or not ((b, ib, pb-1) not in reverse_map or (b, ib, pb+1) not in reverse_map): continue
                if ra['mode'] == rb['mode'] == 1:
                    check = set(c[pa] for c in ra['candidates'] if pa < len(c))&set(c[pb] for c in rb['candidates'] if pb < len(c))
                elif ra['mode'] == 0 and rb['mode'] == 1:
                    check = set(c[pb] for c in rb['candidates'] if pb < len(c))
                elif ra['mode'] == 1 and rb['mode'] == 0:
                    check = set(c[pa] for c in ra['candidates'] if pa < len(c))
                else:
                    continue
                if len(check) == 1:
                    v = check.pop()
                    if ra['mode'] == 1:
                        wa = list(filter(lambda c: pa < len(c) and c[pa]==v, ra['candidates']))
                        if len(wa) == 1 and ((a, ia, pa-1) not in reverse_map or (a, ia, pa+1) not in reverse_map):
                            idx = pa
                            pos = -(pa!=0)
                            for _ in range(len(wa[0])):
                                ni, nj = reverse_map[(a, ia, idx)]
                                hexagons[ni][nj]['v'] = wa[0][pos]
                                idx += 2*(pa==0)-1
                                pos += 2*(pa==0)-1
                    if rb['mode'] == 1:
                        wb = list(filter(lambda c: pb < len(c) and c[pb]==v, rb['candidates']))
                        if len(wb) == 1 and ((b, ib, pb-1) not in reverse_map or (b, ib, pb+1) not in reverse_map):
                            idx = pb
                            pos = -(pb!=0)
                            for _ in range(len(wb[0])):
                                ni, nj = reverse_map[(b, ib, idx)]
                                hexagons[ni][nj]['v'] = wb[0][pos]
                                idx += 2*(pb==0)-1
                                pos += 2*(pb==0)-1

        # Settle middles if possible
        def new_sw(tmp, c):
            if len(tmp) < len(c): return False
            for i in range(len(c)):
                if tmp[i] != '.' and tmp[i] != c[i]: return False
            return True
        def new_ew(tmp, c):
            if len(tmp) < len(c): return False
            for i in range(len(c)):
                if tmp[-i-1] != '.' and tmp[-i-1] != c[-i-1]: return False
            return True
        def derive_candidates(tmp, candidates):
            possible = set()
            def backtrack(tmp_idx):
                if tmp_idx == len(tmp): return possible.add(tuple(tmp))
                for cand in candidates:
                    if tmp_idx+len(cand) > len(tmp): continue
                    # check if you can put here
                    can_put = True
                    for i in range(len(cand)):
                        if cand[i] != tmp[tmp_idx+i] and tmp[tmp_idx+i] != '.': can_put = False; break
                    if can_put:
                        original = []
                        for i in range(len(cand)):
                            original.append(tmp[tmp_idx+i])
                            tmp[tmp_idx+i] = cand[i]
                        backtrack(tmp_idx+len(original))
                        for i in range(len(original)):
                            tmp[tmp_idx+i] = original[i]
            backtrack(0)
            sols = [set() for _ in range(len(tmp))]
            for p in possible:
                for i in range(len(tmp)): sols[i].add(p[i])
            res = ['.']*len(tmp)
            for i in range(len(tmp)):
                if len(sols[i]) == 1: res[i] = sols[i].pop()
            return res
        for ax in 'xyz':
            for k in range(2*n-1):
                if rules[ax][k]['mode'] != 1: continue
                idx = 0
                tmp = []
                while True:
                    t = (ax, k, idx)
                    if t not in reverse_map: break
                    i, j = reverse_map[t]
                    tmp.append(hexagons[i][j].get('v', '.'))
                    idx += 1
                tmp = ''.join(tmp)
                ori_tmp = tmp
                cc = rules[ax][k]['candidates']
                p = 0
                q = len(tmp)
                while tmp:
                    v = [c for c in cc if new_sw(tmp, c)]
                    if len(v) == 1:
                        for kk in range(len(v[0])):
                            i, j = reverse_map[(ax, k, p+kk)]
                            hexagons[i][j]['v'] = v[0][kk]
                        p += len(v[0])
                        tmp = ori_tmp[p:q]
                    else:
                        break
                while tmp:
                    v = [c for c in cc if new_ew(tmp, c)]
                    if len(v) == 1:
                        for kk in range(len(v[0])):
                            i, j = reverse_map[(ax, k, q-len(v[0])+kk)]
                            hexagons[i][j]['v'] = v[0][kk]
                        q -= len(v[0])
                        tmp = ori_tmp[p:q]
                    else:
                        break
                tmp = list(ori_tmp)
                candidates = '^('+'|'.join(cc)+')+$'
                if tmp.count('.') == 1:
                    idx = tmp.index('.')
                    i, j = reverse_map[(ax, k, idx)]
                    if 'v' in hexagons[i][j]: continue
                    ok = []
                    for t in string.ascii_uppercase:
                        tmp[idx] = t
                        if re.match(candidates, ''.join(tmp)): ok.append(t)
                    # check against other axes with mode 1
                    ok2 = []
                    for tt in ok:
                        ok2.append(tt)
                        for ax2 in 'xyz':
                            k2, _ = hexagons[i][j][ax2]
                            tmp2 = []
                            idx = 0
                            tmp2 = []
                            while True:
                                t = (ax2, k2, idx)
                                if t not in reverse_map: break
                                ii, jj = reverse_map[t]
                                if (i, j) == (ii, jj): tmp2.append(tt)
                                else: tmp2.append(hexagons[ii][jj].get('v', '.'))
                                idx += 1
                            if rules[ax2][k2]['mode'] == 0:
                                regex = '.*'.join(['']+rules[ax2][k2]['contains']+[''])
                            else:
                                regex = '^('+'|'.join(rules[ax2][k2]['candidates'])+')+$'
                            if not re.match(regex, ''.join(tmp2)): ok2.pop(); break
                    if len(ok2) == 1: hexagons[i][j]['v'] = ok2[0]
                else:
                    sol = derive_candidates(tmp, cc)
                    if sol == None: continue
                    for m in range(len(sol)):
                        if sol[m] == '.': continue
                        i, j = reverse_map[(ax, k, m)]
                        hexagons[i][j]['v'] = sol[m]

        # Fill gap with mode 0: to be improved
        def derive_gaps(tmp, contains_list):
            if not contains_list: return
            possible = set()
            def backtrack(contains_idx, tmp_idx):
                if contains_idx == len(contains_list): return possible.add(tuple(tmp))
                if tmp_idx >= len(tmp) or tmp_idx+len(contains_list[contains_idx]) > len(tmp): return
                # check if you can put here
                can_put = True
                for i in range(len(contains_list[contains_idx])):
                    if contains_list[contains_idx][i] != tmp[tmp_idx+i] and tmp[tmp_idx+i] != '.': can_put = False; break
                if can_put:
                    original = []
                    for i in range(len(contains_list[contains_idx])):
                        original.append(tmp[tmp_idx+i])
                        tmp[tmp_idx+i] = contains_list[contains_idx][i]
                    backtrack(contains_idx+1, tmp_idx+len(original))
                    for i in range(len(original)):
                        tmp[tmp_idx+i] = original[i]
                backtrack(contains_idx, tmp_idx+1)
            backtrack(0, 0)
            if len(possible) == 1:
                return possible.pop()
        for ax in 'xyz':
            for k in range(2*n-1):
                if rules[ax][k]['mode'] != 0: continue
                contains = '.*'.join(['']+rules[ax][k]['contains']+[''])
                idx = 0
                tmp = []
                while True:
                    t = (ax, k, idx)
                    if t not in reverse_map: break
                    i, j = reverse_map[t]
                    tmp.append(hexagons[i][j].get('v', '.'))
                    idx += 1
                if tmp.count('.') == 1:
                    idx = tmp.index('.')
                    i, j = reverse_map[(ax, k, idx)]
                    if 'v' in hexagons[i][j]: continue
                    ok = []
                    for t in string.ascii_uppercase:
                        tmp[idx] = t
                        if re.match(contains, ''.join(tmp)): ok.append(t)
                    if len(ok) == 1: hexagons[i][j]['v'] = ok[0]
                else:
                    sol = derive_gaps(tmp, rules[ax][k]['contains'])
                    if sol == None: continue
                    for m in range(len(sol)):
                        if sol[m] == '.': continue
                        i, j = reverse_map[(ax, k, m)]
                        hexagons[i][j]['v'] = sol[m]

        # Final sanity check
        filled = 0
        for i in range(2*n-1):
            for h in hexagons[i]:
                filled += 'v' in h
        if filled == 3*n**2-3*n+1: break
    return display()

def format_answer(answer, n=get_size(), space=True):
    idx = 0
    rows = []
    for i in range(2*n-1):
        tmp = [' '*abs(n-1-i)]
        for j in range(2*n-1-abs(n-1-i)):
            tmp.append((answer[idx] if idx < len(answer) else '.')+' '*space)
            idx += 1
        rows.append(''.join(tmp))
    return '\n'.join(rows)

def run(supplier):
    # start browser
    browser = supplier()
    browser.maximize_window()
    browser.set_page_load_timeout(30)
    size = get_size()
    day = get_day()
    try:
        logging.info('Getting HTML source page...')
        link = f'https://regexle.com/?side={size}&day={day}'
        logging.info(link)
        browser.get(link)
        time.sleep(3)
        logging.info('Closing info popup...')
        popups = browser.find_elements(By.ID, 'info_toggle_image')
        for popup in popups:
            if popup.is_displayed():
                ActionChains(browser).click(popup).perform()
                time.sleep(0.5)
    except Exception as e:
        logging.info(f'{type(e).__name__}: {e}')
        browser.quit()
        return run(supplier)

    # parse source page
    t1 = time.time()
    logging.info('Source page obtained! Parsing source page now...')
    soup = BeautifulSoup(browser.page_source, 'html.parser')
    rules = parse(soup)
    logging.info(f'Ruleset obtained!')

    # prep Unregexle
    t2 = time.time()
    answer = solve(rules)
    logging.info('Found answer:\n')
    print(format_answer(answer))
    print()

    # apply solution!
    t3 = time.time()
    hexagons = browser.find_elements(By.CLASS_NAME, 'board_entry')
    chains = ActionChains(browser)
    chains.click(hexagons[0])
    for idx in range(min(len(answer), len(hexagons))):
        chains.send_keys(answer[idx])  
    chains.perform()
    logging.info(f'Solution for Regexle size {size} applied!')
    time.sleep(5)

    # share results! reload browser page
    t4 = time.time()
    contents = []
    soup = BeautifulSoup(browser.page_source, 'html.parser')
    completion = soup.findAll('div', class_='completion_element_center')[1]
    for div_id in ['puzzle_day', 'completion_time', 'hint_count']:
        text = completion.find('div', id=div_id).text.strip().replace('Puzzle:', 'regexle.com')
        if text: contents.append(text)

    assert contents, 'Unregexle is not powerful enough to solve this menace :(\n'
    contents.append(format_answer('🟩'*(3*size**2-3*size+1), space=False).replace(' ', ' '*3))

    browser.quit()
    logging.info(f'All done!')
    return round(t2-t1, 5), round(t3-t2, 5), round(t4-t1, 5), '\n'.join(contents)

if __name__ == '__main__':
    curr_os = (pf:=platform.platform())[:pf.find('-')]
    supplier = {'Windows': get_windows_browser, 'Linux': get_linux_browser}.get(curr_os)
    assert supplier, f'Unregexle not supported for {curr_os} yet :('

    try:
        t_parse, t_algo, t_selenium, verdict = loop_resolve(run, lambda: None, ATTEMPT_LIMIT, supplier)
        print(f'Time to parse Unregexle board: {t_parse}')
        print(f'Time to run backtracking: {t_algo}')
        print(f'Time to apply solution: {t_selenium}')
        print()
        print(verdict.replace(' '*3, ' '))

        # Telebot integration
        for chat_id in CHATS.split(','):
            send(TOKEN, chat_id, f'{verdict}\n\n#unregexle' \
                 .replace('.', '\\.') \
                 .replace('*', '\\*') \
                 .replace('(', '\\(') \
                 .replace(')', '\\)') \
                 .replace('#', '\\#') \
                 .replace('+', '\\+') \
                 .replace('-', '\\-') \
                 .replace('=', '\\=')
                )
    except Exception as e:
        logging.info(f'{type(e).__name__}: {str(e)}')
