// pino-roll не публикует типы; объявляем ровно то подмножество, что используем.
declare module 'pino-roll' {
  import type { DestinationStream } from 'pino';

  interface PinoRollOptions {
    file: string;
    frequency?: 'daily' | 'hourly' | number;
    size?: string | number;
    extension?: string;
    dateFormat?: string;
    limit?: { count?: number };
    symlink?: boolean;
    mkdir?: boolean;
  }

  export default function pinoRoll(options: PinoRollOptions): Promise<DestinationStream>;
}
