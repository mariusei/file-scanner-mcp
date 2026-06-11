/** Liten, stabil fixture for golden-test av scan_directory-formatet. */

export interface Task {
  name: string;
  priority: number;
}

export function byPriority(a: Task, b: Task): number {
  return b.priority - a.priority;
}

export function formatTask(task: Task): string {
  if (task.priority > 5) {
    return `! ${task.name}`;
  }
  return task.name;
}
