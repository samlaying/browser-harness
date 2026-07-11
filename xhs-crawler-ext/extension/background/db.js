const DB_NAME = "xhs-local-crawler";
const DB_VERSION = 1;
const TASKS = "tasks";
const NOTES = "notes";

function openDatabase() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(TASKS)) {
        db.createObjectStore(TASKS, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(NOTES)) {
        const notes = db.createObjectStore(NOTES, { keyPath: "id" });
        notes.createIndex("taskId", "taskId", { unique: false });
        notes.createIndex("noteId", "noteId", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function txStore(name, mode, work) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(name, mode);
    const store = tx.objectStore(name);
    let result;
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
    result = work(store);
  });
}

function requestToPromise(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function putTask(task) {
  return txStore(TASKS, "readwrite", (store) => store.put(task));
}

async function getTask(id) {
  const db = await openDatabase();
  const tx = db.transaction(TASKS, "readonly");
  return requestToPromise(tx.objectStore(TASKS).get(id));
}

async function listTasks() {
  const db = await openDatabase();
  const tx = db.transaction(TASKS, "readonly");
  return requestToPromise(tx.objectStore(TASKS).getAll());
}

async function deleteTask(id) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([TASKS, NOTES], "readwrite");
    tx.objectStore(TASKS).delete(id);
    const idx = tx.objectStore(NOTES).index("taskId");
    const req = idx.openCursor(IDBKeyRange.only(id));
    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor) {
        cursor.delete();
        cursor.continue();
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function putNote(note) {
  return txStore(NOTES, "readwrite", (store) => store.put(note));
}

async function listNotes(taskId) {
  const db = await openDatabase();
  const tx = db.transaction(NOTES, "readonly");
  const idx = tx.objectStore(NOTES).index("taskId");
  return requestToPromise(idx.getAll(taskId));
}

async function clearAll() {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([TASKS, NOTES], "readwrite");
    tx.objectStore(TASKS).clear();
    tx.objectStore(NOTES).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
