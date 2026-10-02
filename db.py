import os
import random
import sqlite3
from datetime import datetime, timedelta

# Vercel's filesystem is read-only except /tmp (data there is ephemeral per instance)
DB_PATH = ("/tmp/studyvault.db" if os.getenv("VERCEL")
           else os.path.join(os.path.dirname(os.path.abspath(__file__)), "studyvault.db"))

SUBJECTS = ["DSA", "DBMS", "Operating Systems", "Computer Networks", "Engineering Maths", "OOP with Java"]
TYPES = ["Notes", "PYQ", "Reference", "Video", "Lab Manual", "Syllabus"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    subject TEXT NOT NULL,
    semester INT,
    type TEXT NOT NULL,
    url TEXT,
    file_path TEXT,
    tags TEXT,
    uploader TEXT,
    upvotes INT DEFAULT 0,
    views INT DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    requested_by TEXT,
    upvotes INT DEFAULT 0,
    fulfilled INT DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# (title, description, subject, semester, type, url, tags, uploader, upvotes, views)
SEED_RESOURCES = [
    ("DSA Unit 2 — Linked Lists & Stacks handwritten notes", "Clean handwritten notes covering singly/doubly linked lists, stack via arrays and lists, infix to postfix conversion with dry runs.", "DSA", 3, "Notes", "https://drive.google.com/file/d/1dsaLinkedListNotes/view", "linked list,stack,infix postfix,pointers", "Aarav Sharma", 96, 812),
    ("DSA PYQ 2023 (VTU) with full solutions", "End-semester 2023 question paper with step-by-step solved answers for trees, graphs and sorting.", "DSA", 3, "PYQ", "https://vtu.ac.in/pyq/dsa-2023-solutions.pdf", "pyq,trees,graphs,sorting,2023", "Priya Nair", 120, 1450),
    ("Trees & Graphs — BFS, DFS, Dijkstra visual guide", "Diagram-heavy reference for tree traversals, BFS/DFS, shortest path and minimum spanning trees.", "DSA", 4, "Reference", "https://www.geeksforgeeks.org/graph-data-structure-and-algorithms/", "trees,graphs,bfs,dfs,dijkstra,mst", "Rohan Gupta", 74, 690),
    ("Abdul Bari — Algorithms full playlist", "Legendary lecture series on asymptotic analysis, divide & conquer, greedy and dynamic programming.", "DSA", 4, "Video", "https://www.youtube.com/playlist?list=PLDN4rrl48XKpZkf03iYFl-O29szjTrs_O", "dynamic programming,greedy,complexity,recursion", "Sneha Iyer", 110, 1320),
    ("DSA Lab Manual — C programs with output", "All 12 lab programs: sorting, searching, stack/queue, BST operations, with sample outputs and viva questions.", "DSA", 3, "Lab Manual", "https://github.com/studyvault/dsa-lab-manual", "lab,c programs,bst,queue,viva", "Karan Mehta", 58, 540),
    ("DSA Hashing & Heaps one-shot revision", "Quick 10-page revision of hashing, collision resolution, heaps and priority queues.", "DSA", 4, "Notes", "https://drive.google.com/file/d/1dsaHashHeapRevision/view", "hashing,heaps,priority queue,revision", "Ananya Rao", 41, 330),

    ("DBMS Unit 3 — Normalization handwritten notes", "1NF to BCNF with worked examples, functional dependencies, closure and candidate keys.", "DBMS", 4, "Notes", "https://drive.google.com/file/d/1dbmsNormalizationNotes/view", "normalization,functional dependency,bcnf,3nf,keys", "Priya Nair", 115, 1280),
    ("DBMS PYQ 2022 + 2023 combined (Mumbai University)", "Two years of question papers with frequently repeated questions highlighted.", "DBMS", 4, "PYQ", "https://mu.ac.in/pyq/dbms-2022-2023.pdf", "pyq,sql,er diagram,transactions", "Aditya Kulkarni", 88, 970),
    ("SQL Queries cheat sheet — joins, subqueries, views", "Two-page cheat sheet with every join type, GROUP BY/HAVING, nested queries and views with examples.", "DBMS", 4, "Reference", "https://www.sqltutorial.org/sql-cheat-sheet/", "sql,joins,subqueries,views,group by", "Rohan Gupta", 79, 860),
    ("Transactions & Concurrency Control explained", "Gate Smashers lectures on ACID, serializability, 2PL and deadlock handling.", "DBMS", 4, "Video", "https://www.youtube.com/playlist?list=PLxCzCOWd7aiFAN6I8CuViBuCdJgiOkT2Y", "transactions,acid,concurrency,serializability,locking", "Sneha Iyer", 67, 720),
    ("DBMS Lab Manual — MySQL experiments", "10 MySQL experiments including DDL, DML, triggers, stored procedures and cursors.", "DBMS", 4, "Lab Manual", "https://github.com/studyvault/dbms-lab-mysql", "lab,mysql,triggers,procedures", "Karan Mehta", 36, 410),
    ("DBMS Syllabus 2024 scheme (unit-wise weightage)", "Official syllabus with unit-wise marks weightage to prioritise revision.", "DBMS", 4, "Syllabus", "https://vtu.ac.in/syllabus/2024/dbms.pdf", "syllabus,weightage,units", "Admin", 22, 260),

    ("OS Process Scheduling — FCFS, SJF, RR solved numericals", "20 solved numericals on scheduling with Gantt charts, waiting and turnaround time.", "Operating Systems", 5, "Notes", "https://drive.google.com/file/d/1osSchedulingNumericals/view", "cpu scheduling,round robin,sjf,gantt chart", "Ananya Rao", 102, 1150),
    ("OS PYQ 2023 (VTU) with solutions", "Solved 2023 paper: deadlocks (Banker's algorithm), paging, page replacement.", "Operating Systems", 5, "PYQ", "https://vtu.ac.in/pyq/os-2023-solutions.pdf", "pyq,deadlock,bankers algorithm,paging,2023", "Aarav Sharma", 97, 1040),
    ("Galvin — Operating System Concepts (key chapters)", "Reference chapters on processes, synchronization, memory management and file systems.", "Operating Systems", 5, "Reference", "https://www.os-book.com/OS10/", "galvin,synchronization,memory management,file systems", "Rohan Gupta", 45, 480),
    ("Memory Management & Paging — Neso Academy", "Video series on paging, segmentation, TLB and virtual memory with page replacement.", "Operating Systems", 5, "Video", "https://www.youtube.com/playlist?list=PLBlnK6fEyqRiVhbXDGLXDk_OQAeuVcp2O", "paging,virtual memory,tlb,page replacement", "Sneha Iyer", 63, 610),
    ("OS Lab — Shell scripting & system calls", "Lab manual with shell scripts, fork/exec, pipes, semaphores and scheduling simulations in C.", "Operating Systems", 5, "Lab Manual", "https://github.com/studyvault/os-lab", "lab,shell,fork,semaphores,system calls", "Karan Mehta", 29, 300),

    ("CN Subnetting cheat sheet", "One-page subnetting, CIDR and VLSM tricks with 15 practice problems.", "Computer Networks", 5, "Reference", "https://www.subnettingpractice.com/cheatsheet.html", "subnetting,cidr,vlsm,ip addressing", "Aditya Kulkarni", 108, 1210),
    ("Computer Networks — OSI & TCP/IP layer notes", "Layer-by-layer notes: framing, error control, routing algorithms, TCP congestion control.", "Computer Networks", 5, "Notes", "https://drive.google.com/file/d/1cnLayerNotes/view", "osi model,tcp ip,routing,congestion control", "Priya Nair", 84, 890),
    ("CN PYQ 2022 (Anna University) solved", "Solved paper with focus on routing protocols, sliding window and CRC problems.", "Computer Networks", 5, "PYQ", "https://annauniv.edu/pyq/cn-2022.pdf", "pyq,routing,sliding window,crc,2022", "Aarav Sharma", 71, 760),
    ("Kurose & Ross lectures — Application to Link layer", "Official lecture videos from the Top-Down Approach textbook authors.", "Computer Networks", 5, "Video", "https://gaia.cs.umass.edu/kurose_ross/lectures.php", "kurose,http,dns,transport layer,tcp", "Ananya Rao", 38, 420),
    ("CN Lab — Packet Tracer & socket programming", "Cisco Packet Tracer topologies and TCP/UDP socket programs in C and Java.", "Computer Networks", 5, "Lab Manual", "https://github.com/studyvault/cn-lab", "lab,packet tracer,socket programming", "Karan Mehta", 33, 350),

    ("Engineering Maths III — Laplace Transform formula sheet", "All Laplace/inverse Laplace formulas, properties and 25 solved examples.", "Engineering Maths", 3, "Notes", "https://drive.google.com/file/d/1mathsLaplaceSheet/view", "laplace transform,inverse laplace,formulas", "Sneha Iyer", 91, 980),
    ("Maths PYQ 2023 — Fourier series & PDE", "Previous paper with solutions for Fourier series, half-range expansions and PDEs.", "Engineering Maths", 3, "PYQ", "https://vtu.ac.in/pyq/maths3-2023.pdf", "pyq,fourier series,pde,2023", "Aditya Kulkarni", 76, 830),
    ("Probability & Statistics — Dr. Gajendra Purohit", "Video lectures on random variables, distributions, correlation and regression.", "Engineering Maths", 4, "Video", "https://www.youtube.com/@gajendrapurohit", "probability,distributions,regression,statistics", "Rohan Gupta", 54, 590),
    ("B.S. Grewal — Higher Engineering Mathematics (chapters)", "Reference chapters with exercises for numerical methods and complex variables.", "Engineering Maths", 4, "Reference", "https://archive.org/details/higher-engineering-mathematics-grewal", "grewal,numerical methods,complex variables", "Admin", 27, 310),

    ("OOP with Java — Inheritance & Polymorphism notes", "Notes on classes, inheritance types, method overriding, abstract classes and interfaces with code.", "OOP with Java", 3, "Notes", "https://drive.google.com/file/d/1javaOOPNotes/view", "inheritance,polymorphism,interfaces,abstract class", "Aarav Sharma", 87, 920),
    ("Java PYQ 2023 with programs", "Solved paper with full programs on exception handling, multithreading and collections.", "OOP with Java", 3, "PYQ", "https://mu.ac.in/pyq/java-2023.pdf", "pyq,exception handling,multithreading,collections,2023", "Priya Nair", 82, 870),
    ("Java Collections Framework cheat sheet", "ArrayList vs LinkedList, HashMap internals, iterators and generics in one page.", "OOP with Java", 4, "Reference", "https://www.baeldung.com/java-collections", "collections,hashmap,generics,arraylist", "Ananya Rao", 49, 520),
    ("Java Lab Manual — 15 programs with viva", "Lab programs on classes, packages, threads, file I/O and JDBC with viva questions.", "OOP with Java", 3, "Lab Manual", "https://github.com/studyvault/java-lab", "lab,jdbc,threads,packages,viva", "Karan Mehta", 31, 340),
    ("OOP with Java — Syllabus & exam pattern", "Official syllabus, module weightage and exam pattern for 2024 scheme.", "OOP with Java", 3, "Syllabus", "https://vtu.ac.in/syllabus/2024/java.pdf", "syllabus,exam pattern,modules", "Admin", 12, 190),
]

# Real PDF uploads shipped in seed_files/ (copied into the upload dir on startup)
# (title, description, subject, semester, type, file_path, tags, uploader, upvotes, views)
SEED_PDFS = [
    ("DBMS Unit 3 Normalization Notes (1NF to BCNF)", "Concise notes on 1NF, 2NF, 3NF and BCNF with PYQ-style exam tips on decomposition, lossless join and dependency preservation.", "DBMS", 4, "Notes", "4ac217a9_dbms_unit3_normalization.pdf", "normalization, bcnf, functional dependency, unit 3", "Ishan Raj", 34, 210),
    ("Data Structures Unit 1: Stacks, Infix/Postfix & Recursion (BMSCE slides)", "Unit 1 lecture slides by Dr. Selva Kumar S, BMSCE. Covers structures, pointers, dynamic memory allocation (malloc/calloc/realloc/free), stack ADT with array implementation, balanced parentheses, infix to postfix/prefix conversion, postfix evaluation, and recursion (factorial, Fibonacci, indirect recursion, Tower of Hanoi) with trace-the-output questions.", "DSA", 3, "Notes", "dee950f9_DSA-BASICS.pdf", "stack, recursion, infix to postfix, dynamic memory, tower of hanoi, unit 1", "Ishan Raj", 28, 175),
]

SEED_REQUESTS = [
    ("Operating Systems", "Solved numericals on Banker's algorithm (more than 5 examples)", "Ishaan", 24),
    ("Computer Networks", "Short notes for Unit 4 — Transport Layer", "Meera", 18),
    ("Engineering Maths", "PYQ 2021 for Maths III with solutions", "Vikram", 15),
    ("DBMS", "ER diagram practice questions with answers", "Diya", 11),
    ("OOP with Java", "Multithreading one-shot video in Hindi", "Rahul", 7),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def seed(conn):
    rnd = random.Random(42)
    now = datetime.utcnow() - timedelta(hours=1)
    for r in SEED_RESOURCES:
        created = (now - timedelta(days=rnd.randint(0, 90), hours=rnd.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO resources (title, description, subject, semester, type, url, file_path, tags, uploader, upvotes, views, created_at)"
            " VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?)",
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], created),
        )
    for r in SEED_PDFS:
        conn.execute(
            "INSERT INTO resources (title, description, subject, semester, type, url, file_path, tags, uploader, upvotes, views)"
            " VALUES (?,?,?,?,?,NULL,?,?,?,?,?)", r)
    for q in SEED_REQUESTS:
        created = (now - timedelta(days=rnd.randint(0, 10))).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO requests (subject, topic, requested_by, upvotes, created_at) VALUES (?,?,?,?,?)",
                     (q[0], q[1], q[2], q[3], created))
    conn.commit()


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 0:
        seed(conn)
    conn.close()
