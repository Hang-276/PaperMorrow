import { spawnSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { join } from 'node:path'

const testDirectory = join(process.cwd(), 'dist', 'tests')
const testFiles = readdirSync(testDirectory)
  .filter((name) => name.endsWith('.test.js'))
  .sort()
  .map((name) => join(testDirectory, name))

if (testFiles.length === 0) {
  throw new Error(`No compiled tests found in ${testDirectory}`)
}

const result = spawnSync(process.execPath, ['--test', ...testFiles], {
  stdio: 'inherit',
})

if (result.error) {
  throw result.error
}
process.exitCode = result.status ?? 1
