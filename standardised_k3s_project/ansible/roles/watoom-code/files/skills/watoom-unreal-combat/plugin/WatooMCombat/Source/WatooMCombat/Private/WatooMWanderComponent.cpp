#include "WatooMWanderComponent.h"
#include "WatooMCombatCharacter.h"
#include "GameFramework/Pawn.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "CollisionQueryParams.h"

UWatooMWanderComponent::UWatooMWanderComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickInterval = 0.f;
}

void UWatooMWanderComponent::BeginPlay()
{
	Super::BeginPlay();
	AActor* Owner = GetOwner();
	Home = LastCheckPos = Owner ? Owner->GetActorLocation() : FVector::ZeroVector;
	WaitLeft = FMath::FRandRange(0.f, WaitMax);   // a crowd placed together does not set off in step
	SetComponentTickEnabled(bEnabled && Owner && Owner->HasAuthority());
}

bool UWatooMWanderComponent::PickTarget()
{
	AActor* Owner = GetOwner();
	for (int32 Try = 0; Try < 8; ++Try)
	{
		const FVector2D R = FMath::RandPointInCircle(Radius);
		FVector P = Home + FVector(R.X, R.Y, 0.f);
		// ground under the point; reject water (below MinGroundZ) and points with no ground at all
		FHitResult Hit;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(WatooMWander), false, Owner);
		if (!GetWorld()->LineTraceSingleByChannel(Hit, P + FVector(0, 0, 5000.f), P - FVector(0, 0, 20000.f), ECC_Visibility, Q)) { continue; }
		if (Hit.ImpactPoint.Z < MinGroundZ) { continue; }
		Target = Hit.ImpactPoint;
		bHasTarget = true;
		return true;
	}
	return false;
}

void UWatooMWanderComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	APawn* Pawn = Cast<APawn>(GetOwner());
	if (!bEnabled || !Pawn) { return; }
	if (const AWatooMCombatCharacter* C = Cast<AWatooMCombatCharacter>(Pawn); C && C->IsDead()) { SetComponentTickEnabled(false); return; }
	if (WaitLeft > 0.f) { WaitLeft -= DeltaTime; return; }
	if (!bHasTarget && !PickTarget()) { WaitLeft = WaitMax; return; }

	const FVector Loc = Pawn->GetActorLocation();
	const FVector To = FVector(Target.X - Loc.X, Target.Y - Loc.Y, 0.f);
	if (To.Size() <= AcceptRadius)
	{
		bHasTarget = false;
		WaitLeft = FMath::FRandRange(WaitMin, WaitMax);
		return;
	}
	Pawn->AddMovementInput(To.GetSafeNormal(), FMath::Clamp(SpeedScale, 0.05f, 1.f));

	StuckClock += DeltaTime;
	if (StuckClock >= StuckSeconds)
	{
		if (FVector::Dist2D(Loc, LastCheckPos) < StuckCm) { bHasTarget = false; }   // blocked: choose another point
		LastCheckPos = Loc;
		StuckClock = 0.f;
	}
}
