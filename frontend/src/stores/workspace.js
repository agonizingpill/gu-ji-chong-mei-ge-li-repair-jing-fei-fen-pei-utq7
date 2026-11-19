import {request} from '../api/client.js';
export const store={data:{},session:JSON.parse(localStorage.getItem('folio-session')||'null')};
export async function reload(){store.data=await request('/workspace');return store.data;}
export async function login(username,password){store.session=await request('/auth/login',{username,password});localStorage.setItem('folio-session',JSON.stringify(store.session));}
export function logout(){localStorage.removeItem('folio-session');location.reload();}
