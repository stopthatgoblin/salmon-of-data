import electricity from './electricity.mjs';
import gas from './gas-api.mjs';

export default {
  fetch(request, env, ctx) {
    return new URL(request.url).pathname.startsWith('/api/gas/')
      ? gas.fetch(request,env,ctx) : electricity.fetch(request,env,ctx);
  },
};
