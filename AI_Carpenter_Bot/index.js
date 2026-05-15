const mineflayer = require('mineflayer')
const fs = require('fs')
const path = require('path')
const { Vec3 } = require('vec3')

// Usage: node index.js <PROJECT_NAME> [OriginX] [OriginY] [OriginZ] [FILENAME]
const projectName = process.argv[2]
const argX = process.argv[3]
const argY = process.argv[4]
const argZ = process.argv[5]
const argFile = process.argv[6] // Optional: e.g. "full_build.json"

if (!projectName) {
    console.error("Please provide a project name argument.")
    process.exit(1)
}

// Path to decoration.json (default) or specified file
// Assumes running from project root or adapting path
const projectDir = path.join(__dirname, '..', 'projects', projectName)
const targetFileName = argFile || 'decoration.json'
const decorationFile = path.join(projectDir, targetFileName)

if (!fs.existsSync(decorationFile)) {
    console.error(`File not found: ${decorationFile}`)
    process.exit(1)
}

console.log(`Loading plan from: ${targetFileName} for project: ${projectName}`)
const plan = JSON.parse(fs.readFileSync(decorationFile, 'utf8'))
const instructions = plan.instructions || []

console.log(`Found ${instructions.length} instructions.`)

const bot = mineflayer.createBot({
    host: process.env.MC_HOST || 'localhost',
    port: parseInt(process.env.MC_PORT || '28888', 10),
    username: 'AI_Carpenter'
})

bot.once('spawn', async () => {
    console.log('🤖 AI Carpenter joined! Ready to work.')
    bot.chat('/gamemode creative')
    await bot.waitForTicks(20)

    await executePlan()
})

async function executePlan() {
    bot.chat('作業を開始します...🔨')

    let origin = null

    // Check if coordinates provided via args
    if (argX && argY && argZ) {
        origin = new Vec3(parseFloat(argX), parseFloat(argY), parseFloat(argZ))
        console.log(`Using provided origin: ${origin}`)
        bot.chat(`指定座標を作業原点とします: ${origin}`)

        // TP Bot to origin so chunks are loaded and it looks cool
        // TP Bot to origin
        // Add small offset to Y and start flying to avoid falling
        bot.chat(`/tp @s ${origin.x} ${origin.y + 5} ${origin.z}`)
        await bot.waitForTicks(20)
        bot.creative.startFlying()
        await bot.waitForTicks(40)
    } else {
        // Fallback: Find player
        const target = bot.nearestEntity(e => e.type === 'player')
        if (!target) {
            console.log("No player found and no coordinates provided.")
            bot.chat("座標指定がなく、プレイヤーも見つかりません。")
            return
        }

        console.log(`Syncing origin with player: ${target.username}`)
        bot.chat(`/tp @s ${target.username}`)
        await bot.waitForTicks(40)
        bot.creative.startFlying()

        origin = target.position.floored()
        console.log(`Origin set to: ${origin}`)
        bot.chat(`プレイヤー位置を原点としました: ${origin}`)
    }

    let count = 0
    const total = instructions.length

    for (const instr of instructions) {
        count++
        const { x, y, z, action, block } = instr

        // Calculate world position
        const targetPos = origin.offset(x, y, z)

        if (action === 'setblock' || action === 'place') {
            // Move if too far
            if (bot.entity.position.distanceTo(targetPos) > 4) {
                // Move to 2 blocks above/near target
                const movePos = targetPos.offset(0, 2, 0)
                bot.chat(`/tp @s ${movePos.x} ${movePos.y} ${movePos.z}`)
                await bot.waitForTicks(20)
            }

            // Look at the target
            await bot.lookAt(targetPos)

            // Use 'replace' explicitly
            const cmd = `/setblock ${targetPos.x} ${targetPos.y} ${targetPos.z} ${block} replace`
            bot.chat(cmd)

            // Log progress occasionally to avoid console spam but verify liveness
            if (count % 5 === 0 || count === 1 || count === total) {
                console.log(`[${count}/${total}] ${cmd}`)
            }
        }

        // Increase delay to avoid rate limiting/kick
        await bot.waitForTicks(5)
    }

    // Rate limit
    await bot.waitForTicks(4)

    bot.chat('装飾完了しました！✨')
    bot.quit()
}

bot.on('error', console.log)
bot.on('kicked', console.log)
