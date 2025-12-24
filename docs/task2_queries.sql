-- Задание 2: примеры SQL-запросов для отчетов
PRAGMA foreign_keys = ON;

-- 1) Список заявок с ключевыми полями
SELECT
  t.request_number,
  t.created_at,
  t.status,
  t.due_at,
  c.full_name AS client_name,
  c.phone AS client_phone,
  a.appliance_type,
  a.appliance_model,
  it.name AS issue_type,
  u.username AS primary_master
FROM tickets t
JOIN clients c ON c.id = t.client_id
JOIN appliances a ON a.id = t.appliance_id
LEFT JOIN issue_types it ON it.id = t.issue_type_id
LEFT JOIN users u ON u.id = t.assigned_specialist_id
ORDER BY t.request_number DESC;

-- 2) Количество выполненных заявок
SELECT COUNT(*) AS completed_count
FROM tickets
WHERE status = 'ready';

-- 3) Среднее время ремонта (в часах) по выполненным заявкам
-- Берем start = started_at, если NULL, то created_at
SELECT
  AVG(
    (julianday(completed_at) - julianday(COALESCE(started_at, created_at))) * 24.0
  ) AS avg_repair_hours
FROM tickets
WHERE status = 'ready' AND completed_at IS NOT NULL;

-- 4) Статистика по типам неисправностей
SELECT
  COALESCE(it.name, 'Не указано') AS issue_type,
  COUNT(*) AS cnt
FROM tickets t
LEFT JOIN issue_types it ON it.id = t.issue_type_id
GROUP BY COALESCE(it.name, 'Не указано')
ORDER BY cnt DESC;

-- 5) Просроченные заявки (не готовые, срок < текущего времени)
SELECT
  t.request_number,
  t.status,
  t.due_at,
  u.username AS primary_master,
  c.full_name AS client_name
FROM tickets t
JOIN clients c ON c.id = t.client_id
LEFT JOIN users u ON u.id = t.assigned_specialist_id
WHERE t.status != 'ready'
  AND t.due_at IS NOT NULL
  AND t.due_at < datetime('now')
ORDER BY t.due_at ASC;

-- 6) Журнал статусов по заявке (пример для заявки №1)
SELECT
  sh.changed_at,
  sh.old_status,
  sh.new_status,
  u.username AS changed_by
FROM status_history sh
JOIN users u ON u.id = sh.changed_by_user_id
JOIN tickets t ON t.id = sh.ticket_id
WHERE t.request_number = 1
ORDER BY sh.id DESC;

-- 7) Комментарии по заявке (пример для заявки №1)
SELECT
  tc.created_at,
  u.username AS author,
  tc.body
FROM ticket_comments tc
JOIN users u ON u.id = tc.user_id
JOIN tickets t ON t.id = tc.ticket_id
WHERE t.request_number = 1
ORDER BY tc.id DESC;

-- 8) Комплектующие по заявке (пример для заявки №1)
SELECT
  tp.created_at,
  tp.part_name,
  tp.quantity
FROM ticket_parts tp
JOIN tickets t ON t.id = tp.ticket_id
WHERE t.request_number = 1
ORDER BY tp.id DESC;

