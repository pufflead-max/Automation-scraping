db = db.getSiblingDB(process.env.MONGO_DB || "PUFF");

db.createUser({
  user: process.env.APP_MONGO_USER || "scraper_admin",
  pwd: process.env.APP_MONGO_PASSWORD || "Mongodb_password12345",
  roles: [{ role: "readWrite", db: db.getName() }]
});
