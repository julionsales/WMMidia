// Executado pelo entrypoint do MongoDB apenas na primeira inicialização (volume vazio).
// Cria um usuário da aplicação com acesso somente ao banco da aplicação.
const dbName = process.env.MONGO_APP_DB || "monitor_automotivo";
const user = process.env.MONGO_APP_USER;
const pwd = process.env.MONGO_APP_PASSWORD;

if (!user || !pwd) {
  throw new Error("MONGO_APP_USER e MONGO_APP_PASSWORD são obrigatórios");
}

const appDb = db.getSiblingDB(dbName);
if (!appDb.getUser(user)) {
  appDb.createUser({ user, pwd, roles: [{ role: "readWrite", db: dbName }] });
  print(`Usuário da aplicação criado em ${dbName}`);
}
