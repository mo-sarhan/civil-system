-- ============================================
-- داتا تجريبية (وهمية بالكامل) للسجل المدني
-- 14 شخص، 5 أجيال
-- ============================================

CREATE TABLE person (
  id            INT PRIMARY KEY,
  national_id   VARCHAR(14) UNIQUE,
  full_name     TEXT NOT NULL,
  gender        CHAR(1),
  birth_date    DATE,
  death_date    DATE,
  birth_place   TEXT,
  father_id     INT REFERENCES person(id),
  mother_id     INT REFERENCES person(id)
);

CREATE TABLE marriage (
  id          INT PRIMARY KEY,
  husband_id  INT REFERENCES person(id),
  wife_id     INT REFERENCES person(id),
  start_date  DATE,
  end_date    DATE
);

-- الجيل 1: الجد والجدة + أزواج وزوجات الجيل التالي (بدون أب/أم في الداتا)
INSERT INTO person VALUES
(1,  '24003151200113', 'محمد أحمد السيد',      'M', '1940-03-15', '2015-06-01', 'القاهرة', NULL, NULL),
(2,  '24507201200224', 'فاطمة علي حسن',        'F', '1945-07-20', NULL,         'القاهرة', NULL, NULL),
(6,  '27011052100628', 'منى إبراهيم يوسف',     'F', '1970-11-05', NULL,         'الجيزة',  NULL, NULL),
(7,  '27201302100729', 'هدى خالد عمر',         'F', '1972-01-30', NULL,         'الجيزة',  NULL, NULL),
(8,  '27006121200811', 'حسن عبد الله مصطفى',   'M', '1970-06-12', NULL,         'القاهرة', NULL, NULL),
(14, '29402021201427', 'دعاء سامي رضا',        'F', '1994-02-02', NULL,         'القاهرة', NULL, NULL);

-- الجيل 2: أولاد محمد وفاطمة
INSERT INTO person VALUES
(3, '26502101200315', 'أحمد محمد أحمد',   'M', '1965-02-10', NULL, 'القاهرة', 1, 2),
(4, '26809011200416', 'محمود محمد أحمد',  'M', '1968-09-01', NULL, 'القاهرة', 1, 2),
(5, '27204251200527', 'سعاد محمد أحمد',   'F', '1972-04-25', NULL, 'القاهرة', 1, 2);

-- الجيل 3: الأحفاد
INSERT INTO person VALUES
(9,  '29205171200912', 'عمر أحمد محمد',     'M', '1992-05-17', NULL, 'القاهرة', 3, 6),
(10, '29508231201023', 'ياسمين أحمد محمد',  'F', '1995-08-23', NULL, 'القاهرة', 3, 6),
(11, '29612021201114', 'يوسف محمود محمد',   'M', '1996-12-02', NULL, 'القاهرة', 4, 7),
(12, '30003091201225', 'نور حسن عبد الله',  'F', '2000-03-09', NULL, 'القاهرة', 8, 5);

-- الجيل 4: ابن الحفيد
INSERT INTO person VALUES
(13, '32010141201316', 'آدم عمر أحمد', 'M', '2020-10-14', NULL, 'القاهرة', 9, 14);

INSERT INTO marriage VALUES
(1, 1, 2,  '1963-05-01', '2015-06-01'),
(2, 3, 6,  '1990-09-10', NULL),
(3, 4, 7,  '1994-04-15', NULL),
(4, 8, 5,  '1998-11-20', NULL),
(5, 9, 14, '2018-12-25', NULL);

-- ============================================
-- استعلامات تجربة
-- ============================================

-- 1) كل نسل محمد أحمد السيد (id = 1)
WITH RECURSIVE descendants AS (
  SELECT id, full_name, 0 AS generation
  FROM person WHERE id = 1
  UNION ALL
  SELECT p.id, p.full_name, d.generation + 1
  FROM person p
  JOIN descendants d ON p.father_id = d.id OR p.mother_id = d.id
)
SELECT * FROM descendants ORDER BY generation, id;

-- 2) أجداد آدم (id = 13)
WITH RECURSIVE ancestors AS (
  SELECT id, full_name, father_id, mother_id, 0 AS generation
  FROM person WHERE id = 13
  UNION ALL
  SELECT p.id, p.full_name, p.father_id, p.mother_id, a.generation + 1
  FROM person p
  JOIN ancestors a ON p.id = a.father_id OR p.id = a.mother_id
)
SELECT * FROM ancestors ORDER BY generation;

-- 3) إخوة عمر (id = 9)
SELECT s.full_name
FROM person me
JOIN person s ON s.id <> me.id
 AND (s.father_id = me.father_id OR s.mother_id = me.mother_id)
WHERE me.id = 9;
