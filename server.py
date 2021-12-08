import argparse
import asyncio
import logging
import os
from functools import partial

import aiofiles
from aiohttp import web


async def get_archive(request, log, delay, folder):
    if log:
        logging.basicConfig(format=u'%(levelname)-8s [%(asctime)s] %(message)s', level=logging.DEBUG)

    archive_hash = request.match_info['archive_hash']

    if not os.path.exists(f'{folder}/{archive_hash}'):
        logging.error(f'Page {folder}/{archive_hash} not found')
        raise web.HTTPNotFound(text='Архив не существует или был удален')

    process = await asyncio.create_subprocess_exec(
        'zip', '-r', '-', archive_hash,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=folder,
    )
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Disposition'] = 'form-data'

    await response.prepare(request)
    try:
        while True:
            stdout = await process.stdout.read(500 * 1024)
            if not stdout:
                await response.write_eof()
                break
            logging.info(f'Sending archive chunk {len(stdout)}')
            await response.write(stdout)
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logging.error(f'Download was interrupted')
        raise
    finally:
        if process.returncode:
            process.kill()
            await process.communicate()
        return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', action='store_true', help='Активировать логгирование')
    parser.add_argument('--delay', type=int, default=0, help='Задержка ответа в секундах')
    parser.add_argument('--folder', type=str, default='archive', help='Папка с фотографиями')
    args = parser.parse_args()
    archive = partial(get_archive, log=args.log, delay=args.delay, folder=args.folder)

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archive),
    ])
    web.run_app(app)