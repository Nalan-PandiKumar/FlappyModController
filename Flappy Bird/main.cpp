#include <iostream>
#include <conio.h>
#include <windows.h>
#include <cstdlib>
#include <ctime>

const int SCREEN_WIDTH = 60;
const int SCREEN_HEIGHT = 20;

const int PLAYER_X = 10;

const int PIPE_COUNT = 3;

const int PIPE_WIDTH = 3;
const int PIPE_CAP_WIDTH = 5;

const int INITIAL_PIPE_SPACING = 25;
const int INITIAL_GAP_SIZE = 7;


// ============================================================
// Structures
// ============================================================

struct Player
{
    int y;
    int velocity;
};

struct Pipe
{
    int x;
    int gapY;
    int gapSize;
    int width;
    bool passed;
};

struct Game
{
    Player player;

    Pipe pipes[PIPE_COUNT];

    int score;
    int pipeSpeed;

    bool gameOver;
};


// ============================================================
// Global game
// ============================================================

Game* game = new Game{};


// ============================================================
// Hide console cursor
// ============================================================

void hideCursor()
{
    HANDLE console =
        GetStdHandle(STD_OUTPUT_HANDLE);

    CONSOLE_CURSOR_INFO cursorInfo;

    GetConsoleCursorInfo(
        console,
        &cursorInfo
    );

    cursorInfo.bVisible = FALSE;

    SetConsoleCursorInfo(
        console,
        &cursorInfo
    );
}


// ============================================================
// Random gap
// ============================================================

int randomGapY()
{
    return 3 + rand() % 8;
}


// ============================================================
// Spawn pipe
// ============================================================

void spawnPipe(Pipe& pipe, int x)
{
    pipe.x = x;

    pipe.gapY = randomGapY();

    pipe.gapSize = INITIAL_GAP_SIZE;

    pipe.width = PIPE_WIDTH;

    pipe.passed = false;
}


// ============================================================
// Initialize game
// ============================================================

void initializeGame()
{
    game->player.y =
        SCREEN_HEIGHT / 2;

    game->player.velocity = 0;

    game->score = 0;

    game->pipeSpeed = 1;

    game->gameOver = false;


    spawnPipe(
        game->pipes[0],
        35
    );

    spawnPipe(
        game->pipes[1],
        35 + INITIAL_PIPE_SPACING
    );

    spawnPipe(
        game->pipes[2],
        35 + INITIAL_PIPE_SPACING * 2
    );
}


// ============================================================
// Player
// ============================================================

void jump()
{
    game->player.velocity = -3;
}


void updatePlayer()
{
    // Gravity.
    game->player.velocity += 1;

    // Move player.
    game->player.y +=
        game->player.velocity;


    // Ceiling.
    if (game->player.y < 0)
    {
        game->player.y = 0;

        game->player.velocity = 0;
    }


    // Ground.
    if (game->player.y >= SCREEN_HEIGHT)
    {
        game->player.y =
            SCREEN_HEIGHT;

        game->player.velocity = 0;

        game->gameOver = true;
    }
}


// ============================================================
// Difficulty
// ============================================================

void updateDifficulty()
{
    game->pipeSpeed =
        1 + game->score / 5;


    // Maximum speed = 2.
    if (game->pipeSpeed > 2)
    {
        game->pipeSpeed = 2;
    }
}


// ============================================================
// Collision
// ============================================================

// bool checkCollision()
// {
//     // Ceiling.
//     if (game->player.y <= 0)
//     {
//         return true;
//     }


//     // Ground.
//     if (game->player.y >= SCREEN_HEIGHT)
//     {
//         return true;
//     }


//     for (int i = 0;
//          i < PIPE_COUNT;
//          i++)
//     {
//         Pipe& pipe =
//             game->pipes[i];


//         // Is the player horizontally
//         // inside this pipe?
//         if (PLAYER_X >= pipe.x &&
//             PLAYER_X < pipe.x + pipe.width)
//         {
//             int gapTop =
//                 pipe.gapY;

//             int gapBottom =
//                 pipe.gapY +
//                 pipe.gapSize;


//             // Player is outside the gap.
//             if (game->player.y < gapTop ||
//                 game->player.y >= gapBottom)
//             {
//                 return true;
//             }
//         }
//     }


//     return false;
// }

bool checkCollision()
{
    // Ceiling.
    if (game->player.y <= 0)
    {
        return true;
    }


    // Ground.
    if (game->player.y >= SCREEN_HEIGHT)
    {
        return true;
    }


    for (int i = 0;
         i < PIPE_COUNT;
         i++)
    {
        Pipe& pipe =
            game->pipes[i];


        // ====================================================
        // Horizontal collision
        // ====================================================

        // Current pipe body position.
        int currentLeft =
            pipe.x;

        int currentRight =
            pipe.x + pipe.width;


        // Position before the last movement.
        int previousLeft =
            pipe.x + game->pipeSpeed;

        int previousRight =
            previousLeft + pipe.width;


        // ----------------------------------------------------
        // The cap is one character wider on each side.
        //
        // Body:
        //     pipe.x ... pipe.x + pipe.width - 1
        //
        // Cap:
        //     pipe.x - 1 ... pipe.x + pipe.width
        // ----------------------------------------------------

        int currentCollisionLeft =
            currentLeft - 1;

        int currentCollisionRight =
            currentRight;

        int previousCollisionLeft =
            previousLeft - 1;

        int previousCollisionRight =
            previousRight;


        // ----------------------------------------------------
        // Check the complete horizontal area travelled by
        // the pipe during this frame.
        // ----------------------------------------------------

        int sweptLeft =
            currentCollisionLeft;

        int sweptRight =
            previousCollisionRight;


        bool horizontalCollision =
            PLAYER_X >= sweptLeft &&
            PLAYER_X <= sweptRight;


        if (!horizontalCollision)
        {
            continue;
        }


        // ====================================================
        // Vertical collision
        // ====================================================

        int gapTop =
            pipe.gapY;

        int gapBottom =
            pipe.gapY +
            pipe.gapSize;


        // ----------------------------------------------------
        // The cap occupies:
        //
        // Top cap    -> y = gapTop - 1
        // Bottom cap -> y = gapBottom
        //
        // Therefore the safe gap is:
        //
        // gapTop ... gapBottom - 1
        // ----------------------------------------------------

        bool insideGap =
            game->player.y >= gapTop &&
            game->player.y < gapBottom;


        if (!insideGap)
        {
            return true;
        }
    }


    return false;
}

// ============================================================
// Update pipes
// ============================================================

void updatePipes()
{
    for (int i = 0;
         i < PIPE_COUNT;
         i++)
    {
        Pipe& pipe =
            game->pipes[i];


        // Move pipe left.
        pipe.x -=
            game->pipeSpeed;


        // ----------------------------------------------------
        // Score
        // ----------------------------------------------------

        if (!pipe.passed &&
            pipe.x + pipe.width < PLAYER_X)
        {
            pipe.passed = true;

            game->score++;

            updateDifficulty();
        }


        // ----------------------------------------------------
        // Recycle pipe
        // ----------------------------------------------------

        if (pipe.x + pipe.width < 0)
        {
            int farthestX = 0;


            for (int j = 0;
                 j < PIPE_COUNT;
                 j++)
            {
                if (game->pipes[j].x >
                    farthestX)
                {
                    farthestX =
                        game->pipes[j].x;
                }
            }


            spawnPipe(
                pipe,
                farthestX +
                INITIAL_PIPE_SPACING
            );
        }
    }
}


// ============================================================
// Draw
// ============================================================

void draw()
{
    // Clear previous frame.
    system("cls");


    // --------------------------------------------------------
    // Game world
    // --------------------------------------------------------

    for (int y = 0;
         y <= SCREEN_HEIGHT;
         y++)
    {
        for (int x = 0;
             x < SCREEN_WIDTH;
             x++)
        {
            bool printed = false;


            // ------------------------------------------------
            // Player
            // ------------------------------------------------

            if (x == PLAYER_X &&
                y == game->player.y)
            {
                std::cout << '@';

                printed = true;
            }


            // ------------------------------------------------
            // Pipes
            // ------------------------------------------------

            if (!printed)
            {
                for (int i = 0;
                     i < PIPE_COUNT;
                     i++)
                {
                    Pipe& pipe =
                        game->pipes[i];


                    int gapTop =
                        pipe.gapY;

                    int gapBottom =
                        pipe.gapY +
                        pipe.gapSize;


                    // ----------------------------------------
                    // Normal pipe body
                    // ----------------------------------------

                    if (x >= pipe.x &&
                        x < pipe.x + pipe.width)
                    {
                        if (y < gapTop ||
                            y >= gapBottom)
                        {
                            std::cout << '#';

                            printed = true;

                            break;
                        }
                    }


                    // ----------------------------------------
                    // Top cap
                    // ----------------------------------------

                    if (y == gapTop - 1)
                    {
                        int capLeft =
                            pipe.x - 1;

                        int capRight =
                            pipe.x +
                            pipe.width;


                        if (x >= capLeft &&
                            x <= capRight)
                        {
                            std::cout << '#';

                            printed = true;

                            break;
                        }
                    }


                    // ----------------------------------------
                    // Bottom cap
                    // ----------------------------------------

                    if (y == gapBottom)
                    {
                        int capLeft =
                            pipe.x - 1;

                        int capRight =
                            pipe.x +
                            pipe.width;


                        if (x >= capLeft &&
                            x <= capRight)
                        {
                            std::cout << '#';

                            printed = true;

                            break;
                        }
                    }
                }
            }


            // ------------------------------------------------
            // Empty space
            // ------------------------------------------------

            if (!printed)
            {
                std::cout << ' ';
            }
        }

        std::cout << '\n';
    }


    // --------------------------------------------------------
    // UI
    // --------------------------------------------------------

    std::cout
        << "------------------------------------------------------------\n";

    std::cout
        << "SPACE = flap | Q = quit\n";

    std::cout
        << "Score: "
        << game->score;

    std::cout
        << "  Y: "
        << game->player.y;

    std::cout
        << "  Velocity: "
        << game->player.velocity;

    std::cout
        << "  Speed: "
        << game->pipeSpeed;

    std::cout << '\n';
}


// ============================================================
// Main
// ============================================================

int main()
{
    // Hide the console cursor.
    hideCursor();


    srand(
        static_cast<unsigned int>(
            time(nullptr)
        )
    );


    initializeGame();


    // --------------------------------------------------------
    // Game loop
    // --------------------------------------------------------

    while (!game->gameOver)
    {
        // ----------------------------------------------------
        // Input
        // ----------------------------------------------------

        if (_kbhit())
        {
            char key =
                _getch();


            if (key == ' ')
            {
                jump();
            }


            if (key == 'q' ||
                key == 'Q')
            {
                break;
            }
        }


        // ----------------------------------------------------
        // Update
        // ----------------------------------------------------

        updatePlayer();

        updatePipes();


        // ----------------------------------------------------
        // Collision
        // ----------------------------------------------------

        if (checkCollision())
        {
            game->gameOver = true;
        }


        // ----------------------------------------------------
        // Render
        // ----------------------------------------------------

        draw();


        // ----------------------------------------------------
        // Game over
        // ----------------------------------------------------

        if (game->gameOver)
        {
            std::cout
                << "\nGAME OVER!\n";


            std::cout
                << "Final Score: "
                << game->score
                << '\n';

            break;
        }


        Sleep(120);
    }


    delete game;

    return 0;
}