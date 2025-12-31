/**
 * Mock Lumino modules for Jest tests.
 */

type Listener<T, U> = (sender: T, args: U) => void;

/**
 * Mock Signal implementation for testing.
 */
export class Signal<T, U> {
  private _listeners: Listener<T, U>[] = [];
  private _sender: T;

  constructor(sender: T) {
    this._sender = sender;
  }

  connect(fn: Listener<T, U>): boolean {
    this._listeners.push(fn);
    return true;
  }

  disconnect(fn: Listener<T, U>): boolean {
    const index = this._listeners.indexOf(fn);
    if (index >= 0) {
      this._listeners.splice(index, 1);
      return true;
    }
    return false;
  }

  emit(args: U): void {
    for (const listener of this._listeners) {
      listener(this._sender, args);
    }
  }

  static clearData(owner: unknown): void {
    // No-op in mock
  }
}

/**
 * ISignal type (interface only, same as Signal for mocking purposes)
 */
export type ISignal<T, U> = Signal<T, U>;

/**
 * Mock Token for dependency injection.
 */
export class Token<T> {
  readonly name: string;
  readonly description: string;

  constructor(name: string, description?: string) {
    this.name = name;
    this.description = description ?? '';
  }
}
