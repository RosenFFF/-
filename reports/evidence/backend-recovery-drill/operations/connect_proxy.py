"""Loopback CONNECT relay: end-to-end official TLS, no certificates or body logging."""
import asyncio
async def handle(reader,writer):
 try:
  head=await reader.readuntil(b'\r\n\r\n')
  if head.split(b'\r\n',1)[0] != b'CONNECT api.deepseek.com:443 HTTP/1.1':
   writer.write(b'HTTP/1.1 403 Forbidden\r\n\r\n');await writer.drain();return
  upstream,remote=await asyncio.open_connection('api.deepseek.com',443)
  writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');await writer.drain()
  async def relay(source,target):
   try:
    while data:=await source.read(65536):target.write(data);await target.drain()
   finally:target.close()
  await asyncio.gather(relay(reader,remote),relay(upstream,writer))
 except (OSError,asyncio.IncompleteReadError,ConnectionError):pass
 finally:writer.close()
async def main():
 server=await asyncio.start_server(handle,'127.0.0.1',8899,limit=8192)
 print('loopback TLS-transparent CONNECT relay ready',flush=True)
 async with server:await server.serve_forever()
asyncio.run(main())
