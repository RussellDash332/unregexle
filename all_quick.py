from main import *

while (t:=int(time.time()%86400))//3600 < 16: # not 4PM GMT yet
    print(t)
    time.sleep(10)
    logging.info(f'Waiting... Current time: {str(t//3600).zfill(2)}:{str(t//60%60).zfill(2)}:{str(t%60).zfill(2)} GMT')

result = []
for side in range(1, 33):
    t_parse, t_algo, _, _, solved = main(day='', n=side, quick=1, spoiler=True)
    result.append((t_parse, t_algo, solved))

unsolved = [i+1 for i in range(len(result)) if not result[i][2]]
max_parse = max((result[i][0], i+1) for i in range(len(result)))
max_algo = max((result[i][1], i+1) for i in range(len(result)))

message = f'''Unsolved Regexle(s): {unsolved}
Maximum time to parse board:\t{max_parse[0]}s for side {max_parse[1]}
Maximum time to backtrack:\t{max_algo[0]}s for side {max_algo[1]}'''

print(message)

for chat_id in CHATS.split(','):
    send(TOKEN, chat_id, f'{message}\n\n#unregexle' \
            .replace('.', '\\.') \
            .replace('*', '\\*') \
            .replace('#', '\\#') \
            .replace('+', '\\+') \
            .replace('-', '\\-') \
            .replace('=', '\\=') \
            .replace('(', '\\(') \
            .replace(')', '\\)') \
            .replace('[', '\\[') \
            .replace(']', '\\]')
        )
