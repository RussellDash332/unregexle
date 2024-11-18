import argparse
import itertools
import logging
import os
import platform
import re
import requests
import string
import sys
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

os.environ['WDM_LOG'] = '0'
try:    TOKEN, CHATS = os.environ['TOKEN'], os.environ['CHATS']
except: from env import TOKEN, CHATS

logging.basicConfig(
    level=logging.INFO, 
    format= '[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)

# Constants
sys.setrecursionlimit(5000)
ATTEMPT_LIMIT = 2

def loop_resolve(f, resolution, lim, *args):
    if lim == 0:
        raise Exception('Reached the limit for number of tries')
    try:
        return f(*args)
    except Exception as e:
        print(f'Issue found: {type(e).__name__}: {str(e)}', flush=True)
        resolution()
        return loop_resolve(f, resolution, lim-1, *args)

def get_windows_browser():
    service = Service()
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    browser = webdriver.Chrome(service=service, options=options)
    return browser

def get_linux_browser():
    chrome_service = Service(ChromeDriverManager(chrome_type='chromium').install())
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
    logging.info(f"{resp.status_code} - {resp.json().get('description')}" if not resp.ok else f"{resp.status_code} - {resp.ok}")

def parse(html, n):
    '''
    The regex values are either in the form of .*r1.*r2.* or (r1|r2)+
    E.g. .*AB.*CDE.*F.* or (ABC|DE|F|G)+
    We will categorize these into two modes: mode 0 or mode 1.

    Note that for mode 1 we can have question marks for optional character and square brackets for choices.
    E.g. (AB?C|DE)+ means (ABC|AC|DE)+, (A[BC]D|EF)+ means (ABD|ACD|EF)+

    For each three axes x, y, and z, there are 2n-1 rules, we will parse these accordingly too.
    '''
    def handle_qn_and_sq(s):
        pre_result = []
        for v in s:
            tmp = ['']
            for i in range(len(v)):
                if v[i] == '?': continue
                if i < len(v)-1 and v[i+1] == '?':
                    tmp = tmp + [x+v[i] for x in tmp]
                else:
                    tmp = [x+v[i] for x in tmp]
            pre_result.extend(tmp)
        result = []
        for blk in pre_result:
            idx = 0
            tmp = ['']
            while idx < len(blk):
                if blk[idx] == '[':
                    idx += 1
                    new_tmp = []
                    while blk[idx] != ']':
                        new_tmp.extend(x+blk[idx] for x in tmp)
                        idx += 1
                    tmp = new_tmp
                else:
                    tmp = [x+blk[idx] for x in tmp]
                idx += 1
            result.extend(tmp)
        return result

    rules = {ax:{} for ax in 'xyz'}
    for hexagon in html.findAll('div', class_='hexagon_center'):
        for ax in 'xyz':
            for k in range(2*n-1):
                for rule in hexagon.findAll('div', id=f'rule_{ax}_{k}'):
                    text = rule.text.strip()
                    if text[0] == '.':
                        rules[ax][k] = (0, [s for s in text.split('.*') if s], text)        # .*r1.*r2.*
                    else:
                        rules[ax][k] = (1, handle_qn_and_sq(text[1:-2].split('|')), text)   # (r1|r2|...)+
    for ax in rules:
        rules[ax] = [rules[ax][k] for k in range(2*n-1)]
    return rules

def solve(rules, n):
    hexagons = [[{} for _ in range(2*n-1-abs(n-1-i))] for i in range(2*n-1)]
    rule2hexagon = {}

    # two-way map hexagon coordinates to x-axis rules
    for i in range(2*n-1):
        r = range(max(i-n+1, 0), min(2*n-1, n+i))
        idx = len(r)-1
        for j in r:
            hexagons[j][i-max(j-n+1, 0)]['x'] = (i, idx)
            rule2hexagon[('x', i, idx)] = (j, i-max(j-n+1, 0))
            idx -= 1

    # two-way map hexagon coordinates to y-axis rules
    for i in range(2*n-1):
        for j in range(2*n-1-abs(n-1-i)):
            hexagons[i][j]['y'] = (i, j)
            rule2hexagon[('y', i, j)] = (i, j)

    # two-way map hexagon coordinates to z-axis rules
    for i in range(2*n-1):
        r = range(max(i-n+1, 0), min(2*n-1, n+i))
        idx = len(r)-1
        for j in r:
            hexagons[-j-1][i-max(j-n+1, 0)]['z'] = (i, idx)
            rule2hexagon[('z', i, idx)] = ((-j-1)%(2*n-1), i-max(j-n+1, 0))
            idx -= 1

    def handle_outer():
        pos = [(i, j) for i in range(2*n-1) for j in range(len(hexagons[i])) if i in (0, 2*n-2) or j in (0, len(hexagons[i])-1)]
        for i, j in pos:
            checks = []
            for ax in 'xyz':
                k, pos = hexagons[i][j][ax]
                rule = rules[ax][k]
                if rule[0] == 1 and ((ax, k, pos-1) not in rule2hexagon or (ax, k, pos+1) not in rule2hexagon):
                    # add either first character or last character for each block
                    checks.append(set(blk[-(pos!=0)] for blk in rule[1]))
            if not checks:
                continue
            candidates = checks[0]
            for k in range(1, len(checks)):
                candidates &= checks[k]
            if len(candidates) == 1:
                v = candidates.pop()
                for ax in 'xyz':
                    k, pos = hexagons[i][j][ax]
                    rule = rules[ax][k]
                    if rule[0] == 1 and ((ax, k, pos-1) not in rule2hexagon or (ax, k, pos+1) not in rule2hexagon):
                        valid_blocks = list(filter(lambda blk: blk[-(pos!=0)] == v, rule[1]))
                        if len(valid_blocks) == 1:
                            # we can fill the other dots with the entire block
                            idx = pos
                            blk = valid_blocks[0]
                            blk_idx = -(pos!=0)
                            delta = 2*(pos==0)-1
                            for _ in range(len(blk)):
                                ni, nj = rule2hexagon[(ax, k, idx)]
                                hexagons[ni][nj]['v'] = blk[blk_idx]
                                idx += delta
                                blk_idx += delta

    def derive_mode_0(tmp, blocks):
        '''
        Example 1:
            tmp = ['.', 'A', 'B', 'C', '.', '.']
            blocks = ['BC', 'EF']

            You should be able to fill EF after the BC since that's the only valid way
            ['.', 'A', 'B', 'C', 'E', 'F']

        Example 2:
            tmp = ['.', '.', '.', 'A']
            blocks = ['B', 'F']

            There are still too many valid outcomes from this, so nothing happens
        '''
        if not blocks:
            return
        sols = [set() for _ in range(len(tmp))]
        def backtrack(block_idx, tmp_idx):
            if block_idx == len(blocks):
                for i in range(len(tmp)):
                    sols[i].add(tmp[i])
                return
            if tmp_idx >= len(tmp) or tmp_idx+len(blocks[block_idx]) > len(tmp):
                return
            can_put = True
            for i in range(len(blocks[block_idx])):
                if blocks[block_idx][i] != tmp[tmp_idx+i] and tmp[tmp_idx+i] != '.':
                    can_put = False
                    break
            if can_put:
                original = []
                for i in range(len(blocks[block_idx])):
                    original.append(tmp[tmp_idx+i])
                    tmp[tmp_idx+i] = blocks[block_idx][i]
                backtrack(block_idx+1, tmp_idx+len(original))
                for i in range(len(original)):
                    tmp[tmp_idx+i] = original[i]
            backtrack(block_idx, tmp_idx+1)
        result = list(tmp)
        backtrack(0, 0)
        for i in range(len(tmp)):
            if len(sols[i]) == 1: result[i] = sols[i].pop()
        return result

    def derive_mode_1(tmp, blocks):
        '''
        Example 1:
            tmp = ['.', 'A', 'B', 'C', '.', '.']
            blocks = ['ABC', 'E', 'FG']

            You should be able to fill the remaining dots since there's only one way to do so
            ['E', 'A', 'B', 'C', 'F', 'G']

        Example 2:
            tmp = ['.', '.', '.', 'A']
            blocks = ['B', 'F']

            There are still too many valid outcomes from this, so nothing happens
        
        Example 3:
            tmp = ['.', 'A', 'B', 'C', '.', '.']
            blocks = ['ABC', 'E', 'FG', 'HI']

            Similar to Example 1 but the 'E' is the only obvious one
            ['E', 'A', 'B', 'C', '.', '.']
        '''
        sols = [set() for _ in range(len(tmp))]
        seen = {}
        def backtrack(tmp_idx, blk):
            if tmp_idx == len(tmp):
                return True
            if tmp_idx+len(blk) > len(tmp):
                return False
            if (tmp_idx, blk) in seen:
                return seen[(tmp_idx, blk)]
            for i in range(len(blk)):
                if blk[i] != tmp[tmp_idx+i] and tmp[tmp_idx+i] != '.':
                    seen[(tmp_idx, blk)] = False
                    return False
            original = []
            for i in range(len(blk)):
                original.append(tmp[tmp_idx+i])
                tmp[tmp_idx+i] = blk[i]
            seen[(tmp_idx, blk)] = False
            for nxt_blk in blocks:
                x = backtrack(tmp_idx+len(blk), nxt_blk)
                if x:
                    seen[(tmp_idx, blk)] = True
                    for i in range(len(blk)):
                        sols[tmp_idx+i].add(blk[i])
            for i in range(len(blk)):
                tmp[tmp_idx+i] = original[i]
            return seen[(tmp_idx, blk)]
        for blk in blocks:
            backtrack(0, blk)
        for i in range(len(tmp)):
            if len(sols[i]) == 1:
                tmp[i] = sols[i].pop()
        return tmp

    def get_current_exp(ax, k, include_pos=False):
        '''
        Helper function to get the state of row `k` in the given axis `ax`
        '''
        idx, tmp, pos = 0, [], []
        while (rule_pos:=(ax, k, idx)) in rule2hexagon:
            i, j = rule2hexagon[rule_pos]
            tmp.append(hexagons[i][j].get('v', '.'))
            pos.append((i, j))
            idx += 1
        if include_pos:
            return tmp, pos
        else:
            return tmp

    def derive_middle():
        for ax in 'xyz':
            for k in range(2*n-1):
                tmp = get_current_exp(ax, k)
                sol = [derive_mode_0, derive_mode_1][rules[ax][k][0]](tmp, rules[ax][k][1])
                if sol != None:
                    for m in range(len(sol)):
                        if sol[m] != '.':
                            i, j = rule2hexagon[(ax, k, m)]
                            hexagons[i][j]['v'] = sol[m]

    def cancel_noise():
        '''
        If there is only one spot left, doesn't hurt to try all 26 uppercase letters!
        This should resolve the issues found on smaller boards with non-unique solutions (e.g. n=2 or n=3)
        '''
        for i in range(2*n-1):
            for j in range(len(hexagons[i])):
                h = hexagons[i][j]
                if 'v' not in h:
                    dots, checks = [], set()
                    for ax in 'xyz':
                        k, _ = h[ax]
                        tmp, pos = get_current_exp(ax, k, include_pos=True)
                        dots.append([pos[x] for x in range(len(tmp)) if tmp[x] == '.'])
                        checks |= {(ax2, hexagons[i2][j2][ax2][0]) for i2, j2 in dots[-1] for ax2 in 'xyz'}
                    flatten_dots = set()
                    for dot in dots:
                        flatten_dots |= set(dot)
                    flatten_dots = list(flatten_dots)
                    if len(flatten_dots) < 4:
                        for u in itertools.product(string.ascii_uppercase, repeat=len(flatten_dots)):
                            for x in range(len(u)):
                                i2, j2 = flatten_dots[x]
                                hexagons[i2][j2]['v'] = u[x]
                            if validate(checks, verbose=False):
                                break
                            for x in range(len(u)):
                                i2, j2 = flatten_dots[x]
                                if 'v' in hexagons[i2][j2]: del hexagons[i2][j2]['v']

    def validate(checks=[(ax, k) for ax in 'xyz' for k in range(2*n-1)], verbose=True):
        '''
        Validate current answer with the regex rules
        '''
        ok = True
        for ax, k in checks:
            tmp = ''.join(get_current_exp(ax, k))
            rule = '^' + rules[ax][k][2] + '$'
            if not re.match(rule, tmp):
                ok = False
                if verbose:
                    print(ax, k, rule, tmp, flush=True)
        return ok

    def display():
        '''
        Helper function to display the current answer based on the state of `hexagons`
        '''
        ans = []
        for i in range(2*n-1):
            for h in hexagons[i]: ans.append(h.get('v', '.'))
        return ''.join(ans)

    def debug_hexagon():
        print(format_answer(display(), n), flush=True)
        print(flush=True)

    # The strategy is to start from the outer hexagons first because it's easier to derive,
    # then continue to derive the remaining hexagons when possible.
    # Repeat for sufficiently many times to handle propagated information
    # and then we should be good!
    for i in range(2*n):
        handle_outer()
        derive_middle()
        if i%2: cancel_noise()
        #debug_hexagon()
    return display(), validate()

def format_answer(answer, n, space=True, spoiler=False):
    idx = 0
    rows = []
    for i in range(2*n-1):
        tmp = ['||'] if spoiler else [' '*abs(n-1-i)]
        for j in range(2*n-1-abs(n-1-i)):
            tmp.append((answer[idx] if idx < len(answer) else '.')+' '*space)
            idx += 1
        if spoiler:
            tmp.append('||')
        rows.append(''.join(tmp))
    return '\n'.join(rows)

def run(n, day, spoiler, quick, supplier):
    # start browser
    browser = supplier()
    browser.maximize_window()
    browser.set_page_load_timeout(20)
    try:
        logging.info('Getting HTML source page...')
        link = f'https://regexle.com/?side={n}&day={day}'
        logging.info(link)
        browser.get(link)
        time.sleep(0.7)
        logging.info('Closing info popup...')
        popups = browser.find_elements(By.ID, 'info_toggle_image')
        for popup in popups:
            if popup.is_displayed():
                ActionChains(browser).click(popup).perform()
                time.sleep(0.3)
    except Exception as e:
        logging.info(f'{type(e).__name__}: {e}')
        browser.quit()
        return run(n, day, spoiler, quick, supplier)

    # parse source page
    t1 = time.time()
    logging.info('Source page obtained! Parsing source page now...')
    soup = BeautifulSoup(browser.page_source, 'html.parser')
    rules = parse(soup, n)
    logging.info(f'Ruleset obtained!')
    for ax in 'xyz':
        print(f'Rules for {ax} axis:', flush=True)
        for rule in rules[ax]:
            print('\t', rule, flush=True)
    print(flush=True)

    # prep Unregexle
    t2 = time.time()
    answer, correct = solve(rules, n)
    logging.info('Candidate answer:\n')
    print(format_answer(answer, n), flush=True)
    print(flush=True)

    # apply solution!
    t3 = time.time()
    if not correct:
        print('Unregexle is not powerful enough to solve this menace :(\n', flush=True)
        return round(t2-t1, 5), round(t3-t2, 5), None, None
    if quick:
        print(f'Unregexle has solved Regexle side={n}\n', flush=True)
        message = '\n'.join([
            f'[regexle.com]({link})',
            format_answer(answer, n, spoiler=True)
        ])
        return round(t2-t1, 5), round(t3-t2, 5), None, None
    hexagons = browser.find_elements(By.CLASS_NAME, 'board_entry')
    chains = ActionChains(browser)
    chains.click(hexagons[0])
    for idx in range(len(answer)):
        if answer[idx] == '.':
            if idx+1 < len(hexagons):
                chains.click(hexagons[idx+1]) # click on the next hexagon
        else:
            chains.send_keys(answer[idx])
        if idx % 100 == 0:
            chains.perform() # to avoid timeout error
    chains.perform()
    logging.info(f'Solution for Regexle side={n} applied!')

    # share results! reload browser page
    t4 = time.time()
    contents = []
    soup = BeautifulSoup(browser.page_source, 'html.parser')
    completion = soup.findAll('div', class_='completion_element_center')[1]
    for div_id in ['puzzle_day', 'completion_time', 'hint_count']:
        text = completion.find('div', id=div_id).text.strip().replace('Puzzle:', f'[regexle.com]({link})')
        if text:
            contents.append(text)

    assert contents, 'Unregexle is not powerful enough to solve this menace :(\n'
    if spoiler:
        contents.append(format_answer(answer, n, spoiler=True))
    else:
        contents.append(format_answer('🟩'*(3*n**2-3*n+1), n, space=False).replace(' ', ' '*3))

    browser.quit()
    logging.info(f'All done!')
    return round(t2-t1, 5), round(t3-t2, 5), round(t4-t3, 5), '\n'.join(contents)

def main(n, day, spoiler, quick):
    curr_os = (pf:=platform.platform())[:pf.find('-')]
    supplier = {'Windows': get_windows_browser, 'Linux': get_linux_browser}.get(curr_os)
    assert supplier, f'Unregexle not supported for {curr_os} yet :('

    t_parse, t_algo, t_selenium, verdict = loop_resolve(run, lambda: None, ATTEMPT_LIMIT, n, day, spoiler, quick, supplier)

    print(f'Time to parse Unregexle board: {t_parse}', flush=True)
    print(f'Time to run backtracking: {t_algo}', flush=True)
    if verdict != None:
        print(f'Time to apply solution: {t_selenium}\n', flush=True)
        print(verdict.replace(' '*3, ' '), flush=True)

        # Telebot integration
        for chat_id in CHATS.split(','):
            send(TOKEN, chat_id, f'{verdict}\n\n#unregexle' \
                    .replace('.', '\\.') \
                    .replace('*', '\\*') \
                    .replace('#', '\\#') \
                    .replace('+', '\\+') \
                    .replace('-', '\\-') \
                    .replace('=', '\\=')
                )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='unregexle', description='Solve Regexle in no time')
    parser.add_argument('-n', '--side', default=3, help='Size of puzzle (1-32)')
    parser.add_argument('-d', '--day', default='', help='Day of puzzle')
    parser.add_argument('-s', '--spoiler', default=0, help='Enable spoilers in output (0 or 1)')
    parser.add_argument('-q', '--quick', default=0, help='Enable quick mode to ignore the Selenium typing part (0 or 1)')
    parser.add_argument('-c', '--cron', default=0, help='Delay solving until new day (0 or 1)')
    args = parser.parse_args()
    n = int(args.side)
    assert 1 <= n <= 32, 'Size must be between 1 and 32 inclusively'

    if int(args.cron):
        while (t:=int(time.time()%86400))//3600 < 16: # not 4PM GMT yet
            time.sleep(10)
            logging.info(f'Waiting... Current time: {str(t//3600).zfill(2)}:{str(t//60%60).zfill(2)}:{str(t%60).zfill(2)} GMT')

    main(n, args.day, int(args.spoiler), int(args.quick))
